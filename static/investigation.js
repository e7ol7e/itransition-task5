/* Browser presentation only. Every detector decision is calculated on the server. */
'use strict';
(() => {
  const byId = id => document.getElementById(id);
  const names = {iqr:'IQR', zscore:'Z-score', moving:'Moving average', grubbs:'Grubbs'};
  const number = value => value === null || value === undefined ? '—' : new Intl.NumberFormat('en-US', {maximumFractionDigits:2, minimumFractionDigits:2}).format(value);
  const el = (tag, text, cls) => {const item=document.createElement(tag); if(text!==undefined)item.textContent=text; if(cls)item.className=cls; return item;};
  const table = (head, rows) => {const wrap=el('div',undefined,'table-scroll'), t=el('table'), h=el('thead'), b=el('tbody'), tr=el('tr'); head.forEach(v=>tr.append(el('th',v))); h.append(tr); rows.forEach(row=>{const r=el('tr'); row.forEach(v=>r.append(el('td',v))); b.append(r);}); t.append(h,b);wrap.append(t);return wrap;};
  let current, selected, sequence=0;
  const dialog = byId('point-inspector');
  const close = () => {sequence++;dialog.close();};
  byId('close-inspector').onclick=close;
  dialog.addEventListener('cancel',()=>sequence++);

  window.inspectObservation = async (series, date) => {
    if(!current)return;
    const request=++sequence, handle=current.report_id;
    byId('inspector-title').textContent=series+' / '+date;
    const body=byId('inspector-body');body.replaceChildren(el('p','Loading the calculations for this snapshot…'));
    if(!dialog.open)dialog.showModal();
    try {
      const response=await fetch('api/inspect/'+handle+'?'+new URLSearchParams({series,date}));
      const data=await response.json();if(!response.ok)throw Error(data.detail||'Inspection failed.');
      if(request!==sequence || handle!==current.report_id)return;
      body.replaceChildren(el('p',number(data.value)+' t · '+(data.flagged?'Flagged by enabled methods':'Not flagged by enabled methods'),'inspector-value'));
      data.tests.forEach(test=>{const block=el('section',undefined,'evidence-rule');
        const verdict=!test.eligible?'Not eligible':test.flagged?'Flagged':'Not flagged';
        block.append(el('h3',names[test.method]+' · '+verdict+(test.enabled?'':' · disabled')),
          el('p',test.calculation));body.append(block);});
      if(data.contributions.length){
        body.append(el('h3','Which mines contributed?'),el('p','Reference: '+data.baseline_kind+'. Contributions reconcile to the network deviation; this is arithmetic attribution, not proof of a cause.'));
        const sum=key=>data.contributions.reduce((total,row)=>total+row[key],0);
        body.append(table(['Mine','Output (t)','Reference (t)','Difference (t)','Injected effect (t)'],[
          ...data.contributions.map(row=>[row.mine,number(row.actual),number(row.baseline),number(row.delta),number(row.event_effect)]),
          ['Network total',number(sum('actual')),number(sum('baseline')),number(sum('delta')),data.injection?number(data.injection.delta):'—']
        ]),el('p','Sum of mine differences '+number(sum('delta'))+' t = network output '+number(data.value)+' − reference '+number(data.baseline)+' t. Totals use unrounded values; displayed rows can differ by a cent.','evidence-note'));
      }
      if(data.injection){const injection=data.injection;
        body.append(el('h3','Simulator comparison'),el('p','Without injected events: '+number(injection.counterfactual)+' t. Net injected effect: '+number(injection.delta)+' t ('+(injection.percent===null?'undefined against zero baseline':number(injection.percent)+'%')+').'),
          el('p','Active event labels: '+(injection.events.join(', ')||'none')+'. '+(injection.material?'Meets the material-effect label.':'Does not meet the material-effect label.')));
      }
      body.append(el('p',data.notes,'evidence-note'),el('p','Snapshot '+data.snapshot,'evidence-note'));
    }catch(error){if(request===sequence)body.replaceChildren(el('p',error.message));}
  };
  byId('inspect-date-form').onsubmit=event=>{event.preventDefault();window.inspectObservation(selected.name,byId('inspect-date').value);};

  document.addEventListener('observatory:render',event=>{
    const previous=current?.report_id; current=event.detail.analysis;selected=event.detail.series;
    if(dialog.open && previous!==current.report_id){sequence++;dialog.close();}
    const dates=current.source.dates, input=byId('inspect-date');
    input.min=dates[0];input.max=dates.at(-1);if(!dates.includes(input.value))input.value=selected.anomalies[0]?.date||dates[0];
    byId('investigation-name').textContent=selected.name==='Total'?'Network total':selected.name;
    const comparison=selected.comparison;
    byId('comparison-body').replaceChildren(table(['Detector','Raw flags','Adds uniquely to enabled union','Selection'],comparison.methods.map(row=>[
      names[row.method],String(row.flagged),row.enabled?String(row.exclusive):'—',row.enabled?'Enabled':'Disabled'
    ])),el('p',comparison.union_count+' distinct dates flagged by enabled methods. Unique additions are dates no other enabled detector flagged. Raw counts and overlaps include disabled detectors.','evidence-note'));
    const matrix=el('details'), summary=el('summary','Pairwise overlap — dates flagged by both detectors');matrix.append(summary,
      table(['Detector',...Object.values(names)],Object.entries(names).map(([key,name])=>[name,...Object.keys(names).map(other=>String(comparison.overlap[key][other]))])));
    byId('comparison-body').append(matrix);
    const validation=selected.validation, target=byId('validation-body');
    if(!validation.available){target.replaceChildren(el('p',validation.reason));return;}
    const union=validation.union;
    target.replaceChildren(el('p','A material event day has an active injected event and a net output change of at least '+validation.threshold_percent+'% and '+validation.minimum_effect+' t against the same-seed, no-event scenario. This is simulator validation, not real-world incident accuracy.'),
      el('p',union.material_hits+' / '+validation.material_days+' material days detected · '+union.material_missed+' missed · '+(union.coverage_percent===null?'coverage not applicable':number(union.coverage_percent)+'% coverage'),'validation-score'),
      table(['Detector','Material days hit','Material days missed','Outside event windows','Weak-effect window flags'],validation.methods.map(row=>[
        names[row.method]+(current.settings.methods.includes(row.method)?'':' (disabled)'),String(row.material_hits),String(row.material_missed),String(row.outside_windows),String(row.weak_window_flags)
      ])),el('p','The enabled union flags '+union.outside_windows+' days outside event windows and '+union.weak_window_flags+' days within weak-effect windows. These flags can reflect noise, weekday patterns, trends or recovery after an event. They are not automatically errors.','evidence-note'),
      table(['Injected event','Starts / days','Peak / probability','Material days','Detected days','Status'],validation.events.map(row=>[
        row.id+' · '+row.name,row.start+' / '+row.duration,number(row.peak)+'× / '+number(row.probability*100)+'%',String(row.material_days),String(row.detected_days),row.status
      ])),el('p','Event coverage counts coincident flags on material days. Overlapping events share their combined net effect; an individual cause cannot be inferred. Neutral, unselected and out-of-range events stay visible.','evidence-note'));
    const link=el('a','Inspect the formula-only Audit tab ↗');link.href=current.source.audit_url;link.target='_blank';link.rel='noopener';if(link.href)target.append(link);
  });
})();
