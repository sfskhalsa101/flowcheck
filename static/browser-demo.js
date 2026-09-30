/* Public demo adapter. No exports or results are sent to a server. */
"use strict";
(function(root) {
  const VERSION = '1.0';
  const HEADER = ['record_id', 'shipment_id', 'sku', 'quantity'];
  const ACTIONS = {
    MISSING_IN_TMS: 'Check the manifest export scope and publishing job; verify the warehouse record before republishing.',
    MISSING_IN_WMS: 'Check for a stale manifest or an incomplete warehouse export; confirm the shipment with the source-system owner.',
    QUANTITY_MISMATCH: 'Compare pick and manifest lines, verify units of measure, and correct the source record before exporting again.'
  };

  function csvRows(text) {
    const rows = []; let row = [], field = '', quoted = false, closed = false;
    const pushField = () => { row.push(field); field = ''; closed = false; };
    const pushRow = () => { pushField(); if (row.length !== 1 || row[0] !== '') rows.push(row); row = []; };
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (quoted) {
        if (c === '"') {
          if (text[i + 1] === '"') { field += '"'; i++; }
          else { quoted = false; closed = true; }
        } else field += c;
      } else if (c === ',') pushField();
      else if (c === '\n' || c === '\r') { if(c === '\r' && text[i+1] === '\n')i++; pushRow(); }
      else if (closed) throw new Error('Malformed CSV: unexpected character after a closing quote.');
      else if (c === '"' && field === '') quoted = true;
      else field += c;
    }
    if (quoted) throw new Error('Malformed CSV: unclosed quoted field.');
    if (field || row.length || closed) pushRow();
    return rows;
  }

  function parseExport(text, source) {
    if (typeof text !== 'string' || !text.trim()) throw new Error(`${source}: an export is required.`);
    if (new TextEncoder().encode(text).length > 500000) throw new Error(`${source}: export exceeds 500 KB.`);
    const rows = csvRows(text.replace(/^\uFEFF/,''));
    if (JSON.stringify(rows.shift()) !== JSON.stringify(HEADER)) throw new Error(`${source}: expected columns in order: ${HEADER.join(',')}`);
    if (!rows.length || rows.length > 5000) throw new Error(`${source}: supply 1–5,000 records.`);
    const seen = new Set();
    return rows.map((fields, index) => {
      const location = `${source}, record ${index+2}`;
      if(fields.length !== 4) throw new Error(`${location}: expected four fields.`);
      fields = fields.map(value => value.trim());
      for (let i=0;i<3;i++) if(!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/.test(fields[i])) throw new Error(`${location}: invalid ${HEADER[i]}. Use letters, numbers, _, . or - (1–64 characters).`);
      if(seen.has(fields[0])) throw new Error(`${location}: duplicate record_id ${fields[0]}; batch rejected to prevent double counting.`);
      if(!/^[0-9]{1,7}$/.test(fields[3]) || Number(fields[3])<1 || Number(fields[3])>1000000) throw new Error(`${location}: quantity must be a whole number from 1 to 1,000,000.`);
      seen.add(fields[0]);
      return {record_id:fields[0],shipment_id:fields[1],sku:fields[2],quantity:Number(fields[3])};
    });
  }

  function reconcile(warehouse, transport) {
    const aggregate = records => {
      const totals = new Map();
      for(const r of records) {const key = r.shipment_id+'\t'+r.sku; totals.set(key,(totals.get(key)||0)+r.quantity);}
      return totals;
    };
    const wms=aggregate(warehouse),tms=aggregate(transport);
    const keys=[...new Set([...wms.keys(),...tms.keys()])].sort();
    const issues=[]; let matched=0;
    for(const key of keys) {
      const [shipment_id,sku]=key.split('\t'), w=wms.get(key)||0,t=tms.get(key)||0;
      const rule=!tms.has(key)?'MISSING_IN_TMS':!wms.has(key)?'MISSING_IN_WMS':w!==t?'QUANTITY_MISMATCH':null;
      if(!rule){matched++;continue;}
      issues.push({shipment_id,sku,rule,warehouse_qty:w,transport_qty:t,delta:t-w,action:ACTIONS[rule]});
    }
    return {summary:{warehouse_records:warehouse.length,transport_records:transport.length,line_keys:keys.length,
      matched_keys:matched,exception_keys:issues.length,warehouse_units:[...wms.values()].reduce((a,b)=>a+b,0),
      transport_units:[...tms.values()].reduce((a,b)=>a+b,0),status:issues.length?'review_required':'matched'},issues};
  }

  // Match Python's sorted-key JSON representation exactly for cross-runtime fingerprints.
  function canonical(warehouse,transport) {
    const encode = rows => '['+rows.slice().sort((a,b)=>a.record_id<b.record_id?-1:a.record_id>b.record_id?1:0).map(r=>
      `{"quantity": ${r.quantity}, "record_id": ${JSON.stringify(r.record_id)}, "shipment_id": ${JSON.stringify(r.shipment_id)}, "sku": ${JSON.stringify(r.sku)}}`).join(', ')+']';
    return `[${JSON.stringify(VERSION)}, ${encode(warehouse)}, ${encode(transport)}]`;
  }

  function exportCSV(run) {
    const fields=['shipment_id','sku','rule','warehouse_qty','transport_qty','delta','action'];
    const escape = value => '"'+String(value).replaceAll('"','""')+'"';
    return fields.join(',')+'\r\n'+run.issues.map(issue=>fields.map(key=>escape(issue[key])).join(',')).join('\r\n');
  }

  function makeAPI(storage, crypto) {
    const key='flowcheck.public-demo.v1';
    function read() {
      try {const runs=JSON.parse(storage.getItem(key)||'[]'); if(!Array.isArray(runs))throw new Error(); return runs;}
      catch {throw new Error('Saved demo history cannot be read. Use a fresh browser profile or clear this site’s browser data.');}
    }
    function save(runs) {
      try {storage.setItem(key,JSON.stringify(runs));}
      catch {throw new Error('Browser storage is full or unavailable. This run was not saved. Use smaller demo exports or allow storage for this site.');}
    }
    async function api(path, options) {
      if(options?.method==='POST' && path==='/api/runs') {
        const {label,warehouse,transport}=JSON.parse(options.body);
        if(typeof label!=='string'||!label.trim()||label.trim().length>80)throw new Error('Snapshot label must contain 1–80 characters.');
        const wms=parseExport(warehouse,'WMS'),tms=parseExport(transport,'TMS');
        const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonical(wms,tms)));
        const fingerprint=Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,'0')).join('');
        // Read after asynchronous hashing; writes are synchronous within this tab.
        const runs=read(),existing=runs.find(r=>r.fingerprint===fingerprint),now=new Date().toISOString();
        if(existing){existing.audit.push({event:'IDENTICAL_SNAPSHOT_REUSED',created_at:now});save(runs);return {...existing,reused:true};}
        const id=runs.reduce((max,r)=>Math.max(max,r.id),0)+1;
        const run={id,label:label.trim(),created_at:now,rule_version:VERSION,fingerprint,...reconcile(wms,tms),
          audit:[{event:'SNAPSHOT_RECONCILED',created_at:now}],source_records:{WMS:wms,TMS:tms}};
        runs.push(run);save(runs);return {...run,reused:false};
      }
      const runs=read();
      if(path==='/api/runs')return runs.slice().reverse().slice(0,100).map(r=>({id:r.id,label:r.label,created_at:r.created_at,...r.summary}));
      const match=path.match(/^\/api\/runs\/(\d+)$/);
      const run=match&&runs.find(r=>r.id===Number(match[1]));
      if(!run)throw new Error('Run not found.');
      return run;
    }
    return api;
  }

  const exported={parseExport,reconcile,canonical,exportCSV,makeAPI};
  if(typeof module!=='undefined'&&module.exports)module.exports=exported;
  else {
    root.FlowCheckCSV=exportCSV;
    root.FlowCheckAPI=async(...args)=>{
      // Accessing localStorage itself may throw in privacy-restricted browsers.
      try {return await makeAPI(root.localStorage,root.crypto)(...args);}
      catch(error){throw new Error(error.message || 'Browser storage is unavailable.');}
    };
  }
})(typeof window==='undefined'?globalThis:window);
