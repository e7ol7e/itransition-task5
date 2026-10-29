"""Deterministic evidence and simulator validation, separate from detection rules."""

import csv
import hashlib
import io
import math
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

MATERIAL_PERCENT = 5.0
MINIMUM_EFFECT = 0.01


def rounded(value):
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def parse_audit(text, parse_data):
    rows = list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))
    if not rows or rows[0][:2] != ["kind", "date_or_id"]:
        raise ValueError("The Audit tab is missing its formula-export header.")
    if any(value.startswith(("#ERROR!", "#REF!", "#VALUE!", "#NAME?", "#N/A")) for row in rows for value in row):
        raise ValueError("The Audit tab contains a formula error; check the generator.")
    events, labels, observations = {}, None, []
    for row in rows[1:]:
        row = row + [""] * max(0, 38 - len(row))
        if not any(row):
            continue
        if row[0] == "event":
            ident = row[1]
            try:
                start = date.fromisoformat(row[3])
                duration, peak, probability = map(float, row[4:7])
                count = int(row[7])
            except (ValueError, IndexError) as exc:
                raise ValueError("Invalid event metadata in the Audit tab.") from exc
            if ident not in {f"E{i}" for i in range(1, 7)} or ident in events or not row[2]:
                raise ValueError("Audit events must have distinct E1..E6 IDs and names.")
            if not all(math.isfinite(v) for v in (duration, peak, probability)) or duration < 1 or peak < 0 or not 0 <= probability <= 1 or not 0 <= count <= 12:
                raise ValueError("Audit event parameters are outside their valid bounds.")
            events[ident] = {"id": ident, "name": row[2], "start": start.isoformat(), "duration": duration, "peak": peak, "probability": probability, "selected_mines": count}
        elif row[0] == "mines":
            if labels is not None:
                raise ValueError("The Audit export contains duplicate mine headers.")
            labels = row[2:14]
        elif row[0] == "observation":
            observations.append(row)
        else:
            raise ValueError("The Audit export has an unexpected row; check its formulas.")
    if len(events) != 6 or labels is None:
        raise ValueError("The Audit export needs all six event slots and mine headers.")
    names = [name for name in labels if name]
    if any(name.strip().lower() == 'total' for name in names):
        raise ValueError('Total is reserved for the network series; give each mine a different name.')
    if labels[:len(names)] != names or any(labels[len(names):]):
        raise ValueError("Active mine slots must be contiguous.")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date"] + names)
    for row in observations:
        writer.writerow([row[1]] + row[2:2 + len(names)])
    snapshot = parse_data(output.getvalue())
    no_event, masks = [], []
    seen = {key: set() for key in events}
    for index, row in enumerate(observations):
        day = date.fromisoformat(row[1])
        baseline, day_masks = [], []
        for mine in range(len(names)):
            try:
                nominal = float(row[14 + mine])
            except ValueError as exc:
                raise ValueError("Missing no-event output in the Audit tab.") from exc
            if not math.isfinite(nominal) or nominal < 0 or nominal > 1e12:
                raise ValueError("No-event output must be finite and between 0 and 1e12.")
            ids = row[26 + mine].split("|") if row[26 + mine] else []
            if len(set(ids)) != len(ids) or any(key not in events for key in ids):
                raise ValueError("Unknown or repeated injected-event label.")
            multiplier = 1.0
            for ident in ids:
                event = events[ident]
                elapsed = (day - date.fromisoformat(event["start"])).days
                if not 0 <= elapsed < event["duration"] or event["peak"] == 1 or event["selected_mines"] == 0:
                    raise ValueError("An event label falls outside its active window.")
                sigma = max(0.25, event["duration"] / 6)
                multiplier *= 1 + (event["peak"] - 1) * math.exp(-0.5 * ((elapsed - (event["duration"] - 1) / 2) / sigma) ** 2)
                seen[ident].add(mine)
            expected = nominal * multiplier
            actual = snapshot["values"][index][mine]
            if not math.isfinite(expected) or abs(actual - expected) > 0.011 + abs(expected) * 1e-12:
                raise ValueError("Observed output does not reconcile with the no-event baseline and event labels. Refresh after spreadsheet recalculation.")
            baseline.append(nominal)
            day_masks.append(ids)
        no_event.append(baseline)
        masks.append(day_masks)
    first, last = map(date.fromisoformat, (snapshot["dates"][0], snapshot["dates"][-1]))
    for ident, event in events.items():
        start = date.fromisoformat(event["start"])
        intersects = start <= last and (first - start).days < event["duration"]
        if event["selected_mines"] > len(names) or (intersects and event["peak"] != 1 and len(seen[ident]) != event["selected_mines"]):
            raise ValueError("Affected mine labels do not match the formula-selected mine count.")
    snapshot["data_snapshot"] = snapshot["snapshot"]
    canonical = repr((snapshot["snapshot"], events, no_event, masks))
    snapshot["snapshot"] = hashlib.sha256(canonical.encode()).hexdigest()[:16]
    snapshot["audit"] = {"events": list(events.values()), "no_event": no_event, "masks": masks}
    return snapshot


def enrich(result, snapshot):
    settings = result["settings"]
    audit = snapshot.get("audit")
    for number, series in enumerate(result["series"]):
        sets = {key: set(values) for key, values in series["flags"].items()}
        selected = set().union(*(sets[key] for key in settings["methods"]))
        series["comparison"] = {
            "union_count": len(selected),
            "methods": [{"method": key, "enabled": key in settings["methods"], "flagged": len(indices),
                         "exclusive": len(indices - set().union(*(sets[other] for other in settings["methods"] if other != key))) if key in settings["methods"] else 0}
                        for key, indices in sets.items()],
            "overlap": {key: {other: len(indices & other_indices) for other, other_indices in sets.items()} for key, indices in sets.items()},
        }
        if not audit:
            series["validation"] = {"available": False, "reason": "This snapshot has no formula-audited event labels."}
            continue
        days = []
        for index, actual in enumerate(series["values"]):
            nominal = sum(audit["no_event"][index]) if number == 0 else audit["no_event"][index][number - 1]
            ids = sorted(set().union(*(set(ids) for ids in audit["masks"][index]))) if number == 0 else audit["masks"][index][number - 1]
            counterfactual = rounded(nominal)
            delta = rounded(actual - counterfactual)
            percent = abs(delta) / abs(counterfactual) * 100 if counterfactual else (0.0 if delta == 0 else None)
            material = bool(ids) and abs(delta) >= MINIMUM_EFFECT and (percent is None or percent >= MATERIAL_PERCENT)
            days.append({"counterfactual": counterfactual, "delta": delta, "percent": percent, "events": ids, "material": material})
        material_days = {i for i, day in enumerate(days) if day["material"]}
        windows = {i for i, day in enumerate(days) if day["events"]}

        def score(indices):
            return {"flagged": len(indices), "material_hits": len(indices & material_days), "material_missed": len(material_days - indices),
                    "outside_windows": len(indices - windows), "weak_window_flags": len((indices & windows) - material_days),
                    "coverage_percent": len(indices & material_days) / len(material_days) * 100 if material_days else None}

        events = []
        for event in audit["events"]:
            event_days = {i for i, day in enumerate(days) if event["id"] in day["events"]}
            eligible = event_days & material_days
            status = "Detected" if eligible & selected else "Missed" if eligible else "No material days"
            if event["peak"] == 1:
                status = "Neutral multiplier"
            elif event["selected_mines"] == 0:
                status = "No mines selected"
            elif not event_days:
                status = "Outside range / not this mine"
            events.append({**event, "window_days": len(event_days), "material_days": len(eligible), "detected_days": len(eligible & selected),
                           "status": status, "methods": {key: len(indices & eligible) for key, indices in sets.items()}})
        series["validation"] = {"available": True, "threshold_percent": MATERIAL_PERCENT, "minimum_effect": MINIMUM_EFFECT,
                                "days": days, "window_days": len(windows), "material_days": len(material_days),
                                "union": score(selected), "methods": [{"method": key, **score(indices)} for key, indices in sets.items()], "events": events}
    return result


def inspect_day(result, name, day):
    series = next((s for s in result["series"] if s["name"] == name), None)
    if series is None or day not in result["source"]["dates"]:
        raise ValueError("Choose a series and date from this analysis snapshot.")
    index = result["source"]["dates"].index(day)
    value, stats, config = series["values"][index], series["stats"], result["settings"]
    lower, upper = series["bounds"]["iqr_lower"], series["bounds"]["iqr_upper"]
    has_sd = stats["std"] > 1e-12
    z = abs(value - stats["mean"]) / stats["std"] if has_sd else 0.0
    baseline = series["moving_average"][index]
    rows = [
        {"method": "iqr", "calculation": f"{value:.6f} t compared with [{lower:.6f}, {upper:.6f}] t. Q1={stats['q1']:.6f}; Q3={stats['q3']:.6f}; IQR={stats['iqr']:.6f}; multiplier={config['iqr_factor']}.", "eligible": True},
        {"method": "zscore", "calculation": f"abs({value:.6f} - {stats['mean']:.6f}) / {stats['std']:.6f} = {z:.6f}; threshold > {config['z_threshold']}." if has_sd else "Constant series: standard deviation is numerically zero (<= 1e-12); no z-score flag.", "eligible": has_sd},
        {"method": "moving", "calculation": f"Warm-up: requires {config['moving_window']} prior days; only {index} available.", "eligible": baseline is not None},
    ]
    if baseline is not None:
        if baseline == 0:
            rows[2]["calculation"] = f"Previous {config['moving_window']} days average 0 t. {'Positive output against zero baseline is flagged; percentage is undefined.' if value > 0 else 'Output is also zero; no flag.'}"
        else:
            distance = abs(value - baseline) / abs(baseline) * 100
            rows[2]["calculation"] = f"abs({value:.6f} - {baseline:.6f}) / abs({baseline:.6f}) × 100 = {distance:.6f}%; threshold > {config['moving_percent']}%. Tested day excluded."
    passes = series.get("grubbs_passes", [])
    details = []
    for step in passes:
        if step.get("candidate_index") is None:
            details.append("Constant remaining sample; no Grubbs rejection.")
            break
        candidate = result["source"]["dates"][step["candidate_index"]]
        details.append(f"Pass {step['pass']}: n={step['n']}, candidate {candidate}; maximum G={step['score']:.6f}, critical={step['critical']:.6f}; {'rejected' if step['rejected'] else 'not rejected'}. This day {'is' if step['candidate_index'] == index else 'is not'} that candidate.")
        if step["candidate_index"] == index and step["rejected"]:
            break
    rows.append({"method": "grubbs", "calculation": " ".join(details) or "No eligible Grubbs pass.", "eligible": any(step.get('candidate_index') is not None for step in passes)})
    for row in rows:
        row.update(enabled=row["method"] in config["methods"], flagged=index in series["flags"][row["method"]])
    contributions = []
    if name == "Total":
        for mine in result["series"][1:]:
            reference = mine["moving_average"][index] if baseline is not None else mine["stats"]["mean"]
            validation = mine["validation"]
            truth = validation["days"][index] if validation["available"] else None
            contributions.append({"mine": mine["name"], "actual": mine["values"][index], "baseline": reference,
                                  "delta": mine["values"][index] - reference, "event_effect": truth["delta"] if truth else None})
        contributions.sort(key=lambda row: abs(row["delta"]), reverse=True)
    validation = series["validation"]
    return {"snapshot": result["source"]["snapshot"], "series": name, "date": day, "value": value,
            "flagged": any(row["enabled"] and row["flagged"] for row in rows), "tests": rows,
            "baseline": baseline if baseline is not None else stats["mean"], "baseline_kind": f"Previous {config['moving_window']} days" if baseline is not None else "Full-series mean (moving-window warm-up)",
            "contributions": contributions, "injection": validation["days"][index] if validation["available"] else None,
            "notes": "These are retrospective statistical flags, not confirmed incidents. Detector agreement is not an independent confidence score. Event effects describe this simulator only."}
