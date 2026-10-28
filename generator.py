"""Build the cell formulas for the Google Sheets generator. No Apps Script is used.

This file prepares reproducible setup artifacts; all production generation happens
inside Google Sheets, including autoregression, seasonality, trend and events.
"""
from __future__ import annotations

import csv
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SHEET_ID = "1uxxmH3IpLPEGzf8j6foVFvSr1yaU-W55qWbIQEBUWQ0"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
NAMES = ["LV-426", "Origae-6", "Fiorina 161", "Acheron", "Hadley's Hope", "Thedus",
         "Calpamos", "G-435", "Anchorpoint", "Sevastopol", "Tartarus", "LV-223"]


def parameters():
    rows = [[""] * 12 for _ in range(43)]
    def row(number, *values):
        rows[number - 1][:len(values)] = values
    row(1, "WEYLAND-YUTANI", "MINING OPERATIONS / GENERATOR")
    row(2, "Change the amber cells. Data and chart recalculate automatically; no script is required.")
    row(3, "SIMULATION", "VALUE", "GUIDANCE", "WEEKDAY", "FACTOR", "", "MINE INVENTORY", "CAPACITY FACTOR")
    row(4, "Active mines", 6, "1 to 12; activate named slots in G4:G15", "Monday", 1, "", NAMES[0], 1)
    row(5, "Start date", "=DATE(2099,1,1)", "Inclusive; dates are actual date values", "Tuesday", 1, "", NAMES[1], 0.85)
    row(6, "End date", "=DATE(2099,6,29)", "Inclusive; 3 to 730 days", "Wednesday", 1.03, "", NAMES[2], 1.2)
    row(7, "Distribution", "Normal", "Normal or Uniform (innovation distribution)", "Thursday", 1.02, "", NAMES[3], 0.92)
    row(8, "Normal mean", 100, "Used only when Normal is selected", "Friday", 0.97, "", NAMES[4], 1.1)
    row(9, "Normal std deviation", 12, "Positive; measured before capacity / trend", "Saturday", 0.8, "", NAMES[5], 0.76)
    row(10, "Uniform minimum", 75, "Used only when Uniform is selected", "Sunday", 0.6, "", NAMES[6], 1.05)
    row(11, "Uniform maximum", 125, "Must exceed the minimum", "", "", "", NAMES[7], 0.98)
    row(12, "Correlation rho", 0.86, "0 to 0.99; larger = smoother / more persistent", "", "", "", NAMES[8], 0.8)
    row(13, "Daily trend rate", 0.001, "0.001 means +0.1% per day (compounded)", "", "", "", NAMES[9], 1.15)
    row(14, "Random seed", 2026, "Change this integer for another reproducible scenario", "", "", "", NAMES[10], 0.9)
    row(15, "Active mean", '=IF(B7="Normal",B8,AVERAGE(B10:B11))', "Read-only: follows the chosen distribution", "", "", "", NAMES[11], 1.08)
    row(16, "Active std deviation", '=IF(B7="Normal",B9,(B11-B10)/SQRT(12))', "Read-only: follows the chosen distribution")
    row(17, "Days generated", '=MAX(3,MIN(730,B6-B5+1))', "Guarded to 3..730 days")
    row(18, "Active parameter labels", '=IF(B7="Normal","Mean / standard deviation","Minimum / maximum")')
    row(19, "Configuration status", '=IFERROR(IF(AND(B4=INT(B4),B4>=1,B4<=12,ISNUMBER(B5),ISNUMBER(B6),B6-B5+1>=3,B6-B5+1<=730,OR(B7="Normal",B7="Uniform"),B8>=0,B9>=0,B10>=0,B11>B10,B12>=0,B12<=0.99,B13>-1,B13<=0.1,B14=INT(B14),COUNT(E4:E10)=7,MIN(E4:E10)>=0,COUNT(H4:H15)=12,MIN(H4:H15)>=0,COUNT(C22:C27)=6,MIN(C22:C27)>=1,COUNT(D22:D27)=6,MIN(D22:D27)>=0,COUNT(E22:E27)=6,MIN(E22:E27)>=0,MAX(E22:E27)<=1,COUNTA(G4:INDEX(G4:G15,B4))=B4,COUNTUNIQUE(G4:INDEX(G4:G15,B4))=B4,COUNTIF(G4:INDEX(G4:G15,B4),"Total")=0),"READY","CHECK INPUTS"),"CHECK INPUTS")', "Read-only: invalid settings stop Data generation with a clear message.")
    row(20, "EVENTS / BELL-SHAPED MULTIPLIERS")
    row(21, "Event name", "Start date", "Duration (days)", "Peak factor", "Mine probability", "NOTES")
    for index, (name, offset, duration, factor, probability) in enumerate([
        ("Refinery outage", 24, 7, 0.15, 1), ("Rich ore seam", 58, 5, 2.3, 0.65),
        ("Dust storm", 94, 9, 0.3, 0.8), ("New extraction rig", 130, 6, 1.9, 0.5),
        ("Optional event 5", 155, 4, 1, 1), ("Optional event 6", 165, 4, 1, 0.5)
    ]):
        row(22 + index, name, f"=$B$5+{offset}", duration, factor, probability,
            "<1 drop; >1 spike; 1 disabled. Probability is decided once per event and mine.")
    row(29, "HOW TO USE")
    row(30, "1", "Edit B4 for mine count, G4:G15 for names, H4:H15 for relative capacity.")
    row(31, "2", "Choose Normal or Uniform in B7. Active labels and moments update in B15:B18.")
    row(32, "3", "Use rho B12 to correlate days; weekday factors E4:E10 and daily trend B13 add structure.")
    row(33, "4", "Configure at least four events in rows 22:27. Change seed B14 to reroll mine selection and noise.")
    row(34, "5", "Open Data for the live formula output and chart. The dashboard Refresh button reads this sheet.")
    row(35, "6", "Output = nonnegative AR(1) baseline x capacity x weekday x compound trend x event multipliers.")
    row(36, "MODEL NOTES")
    row(37, "Smoothing", "x(t)=mu+rho*(x(t-1)-mu)+sqrt(1-rho^2)*innovation(t), initialized at mu.")
    row(38, "Distributions", "Normal / uniform describe innovations; smoothing and calendar factors transform final output.")
    row(39, "Events", "A Gaussian envelope is truncated to the configured duration; overlapping events multiply.")
    row(40, "Reproducibility", "Seeded SIN/MOD pseudo-random cells are stable when unrelated cells change; no volatile RAND().")
    row(41, "Limits", "Up to 12 mines and 730 days. Output is tonnes/day; negative baselines are clipped to zero.")
    row(42, "Dashboard", "https://task5.evgeniy.win/")
    row(43, "Source code", "https://github.com/e7ol7e/itransition-task5")
    return rows


def data_formula(index):
    # Fixed identifiers deliberately avoid A1/R1C1-style LAMBDA names.
    col = chr(66 + index)
    slot = index + 1
    uniform = f"MAX(0.000001,MIN(0.999999,MOD(SIN((tick+Parameters!$B$14*97+{slot}*991)*12.9898)*43758.5453,1)))"
    events = []
    for number in range(22, 28):
        chance = f"MOD(SIN((Parameters!$B$14+{slot}*113+{number}*7919)*78.233)*43758.5453,1)"
        start, duration = f"Parameters!$B${number}", f"Parameters!$C${number}"
        factor, probability = f"Parameters!$D${number}", f"Parameters!$E${number}"
        event = (f"IF(AND(day>={start},day<{start}+{duration},{chance}<{probability}),"
                 f"1+({factor}-1)*EXP(-0.5*((day-({start}+({duration}-1)/2))/MAX(0.25,{duration}/6))^2),1)")
        events.append(event)
    return (f'=IF(OR({col}1="",Parameters!$B$19<>"READY"),"",LET(mu,Parameters!$B$15,rho,MAX(0,MIN(0.99,Parameters!$B$12)),'
            f'baseline,SCAN(mu,SEQUENCE(Parameters!$B$17),LAMBDA(prev,tick,'
            f'mu+rho*(prev-mu)+SQRT(1-rho^2)*IF(Parameters!$B$7="Normal",'
            f'Parameters!$B$9*NORM.S.INV({uniform}),(Parameters!$B$11-Parameters!$B$10)*({uniform}-0.5)))),'
            f'MAP(SEQUENCE(Parameters!$B$17),baseline,LAMBDA(tick,noise,LET(day,Parameters!$B$5+tick-1,'
            f'ROUND(MAX(0,noise)*Parameters!$H${4+index}*INDEX(Parameters!$E$4:$E$10,WEEKDAY(day,2))*'
            f'(1+Parameters!$B$13)^(tick-1)*' + '*'.join(events) + ',2))))))')


def data():
    rows = [["Date"] + [f'=IF(Parameters!$B$4>={i+1},Parameters!G{i+4},"")' for i in range(12)] + ["Total"]]
    rows.append(['=IF(Parameters!B19<>"READY","CHECK INPUTS ON PARAMETERS TAB",ARRAYFORMULA(TEXT(SEQUENCE(Parameters!B17,1,Parameters!B5,1),"yyyy-mm-dd")))'] +
                [data_formula(i) for i in range(12)] +
                ['=IF(Parameters!B19="READY",BYROW(B2:INDEX(M:M,Parameters!B17+1),LAMBDA(values,SUM(values))),"")'])
    return rows


def clipboard_html(rows, kind):
    """Rich-text paste gives the live spreadsheet a readable control-panel layout."""
    parts = ['<table style="font-family:Arial;font-size:11pt;color:#263531">']
    for i, row in enumerate(rows, 1):
        parts.append('<tr>')
        for j, value in enumerate(row):
            dark = i in ({1, 3, 20, 21, 29, 36} if kind == "Parameters" else {1})
            editable = kind == "Parameters" and ((j == 1 and 4 <= i <= 14) or
                        (j == 4 and 4 <= i <= 10) or (j in (6, 7) and 4 <= i <= 15) or
                        (j in (0, 1, 2, 3, 4) and 22 <= i <= 27))
            bg = '#173e36' if dark else '#fff0cd' if editable else '#f3f7f2' if i % 2 else '#ffffff'
            color = '#ffffff' if dark else '#263531'
            text = html.escape(str(value))
            parts.append(f'<td style="background-color:{bg};color:{color};font-weight:{"bold" if dark or j==0 else "normal"};padding:8px;border:1px solid #dbe4dc">{text}</td>')
        parts.append('</tr>')
    return ''.join(parts) + '</table>'


def main():
    out = ROOT / 'generator'
    out.mkdir(exist_ok=True)
    for name, rows in (("Parameters", parameters()), ("Data", data())):
        with (out / f'{name}.tsv').open('w', newline='', encoding='utf-8') as stream:
            csv.writer(stream, delimiter='\t', lineterminator='\n').writerows(rows)
        (out / f'{name}.html').write_text(clipboard_html(rows, name), encoding='utf-8')
    (out / 'cells.json').write_text(json.dumps({'Parameters': parameters(), 'Data': data()}), encoding='utf-8')
    print('Prepared formula-only generator:', SHEET_URL)


if __name__ == '__main__':
    main()
