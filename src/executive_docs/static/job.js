const terminal=new Set(['READY_FOR_REVIEW','APPROVED_FINAL','FAILED_ANALYSIS','FAILED_GENERATION','FAILED_VALIDATION','CANCELLED']);
const show=(id,on=true)=>document.getElementById(id).classList.toggle('hidden',!on);
const esc=value=>String(value??'').replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
const safePath=value=>String(value).split('/').map(encodeURIComponent).join('/');
let currentJob=null;

async function api(url,options={}){
  const response=await fetch(url,{headers:{'Content-Type':'application/json'},...options});
  if(!response.ok)throw new Error((await response.json()).detail||response.statusText);
  return response.json();
}

async function refresh(){
  const job=await api(`/api/jobs/${jobId}`);
  currentJob=job;
  document.getElementById('status').textContent=job.status;
  document.getElementById('summary').textContent=job.summary||job.error||'';
  document.getElementById('revision').textContent=job.revision;
  document.getElementById('profile').textContent=job.processing_profile;
  const usage=job.model_usage||[];
  const input=usage.reduce((sum,item)=>sum+(item.input_tokens||0),0);
  const cached=usage.reduce((sum,item)=>sum+(item.cached_tokens||0),0);
  const output=usage.reduce((sum,item)=>sum+(item.output_tokens||0),0);
  const unknownCost=usage.some(item=>item.estimated_cost_usd===null);
  const knownCost=usage.reduce((sum,item)=>sum+(item.estimated_cost_usd||0),0);
  const costLabel=unknownCost?'оценка USD недоступна':`оценка $${knownCost.toFixed(3)}`;
  document.getElementById('usage-summary').textContent=usage.length?`${usage.length} выз. · вход ${input.toLocaleString('ru-RU')} · кэш ${cached.toLocaleString('ru-RU')} · выход ${output.toLocaleString('ru-RU')} · ${costLabel}`:'Платных вызовов пока не было.';
  show('progress',!terminal.has(job.status)&&job.status!=='NEEDS_INPUT');
  show('questions',job.status==='NEEDS_INPUT');
  if(job.status==='NEEDS_INPUT'){
    document.getElementById('question-list').innerHTML=job.questions.map(q=>`<label>${esc(q.prompt)}<small>${esc(q.reason)}</small><input name="${esc(q.id)}" value="${esc(q.answer)}" required><textarea data-comment="${esc(q.id)}" placeholder="Основание или комментарий">${esc(q.comment)}</textarea></label>`).join('');
  }
  show('issues',job.validation_issues.length>0);
  document.getElementById('issue-list').innerHTML=job.validation_issues.map(issue=>`<div class="issues ${esc(issue.severity)}"><b>${esc(issue.code)}</b><br>${esc(issue.message)}</div>`).join('');
  const previews=await api(`/api/jobs/${jobId}/preview`);
  show('previews',previews.files.length>0);
  document.getElementById('preview-list').innerHTML=previews.files.map(file=>`<a target="_blank" rel="noopener" href="/api/jobs/${jobId}/files/${safePath(file)}">${esc(file.split('/').pop())}</a>`).join('');
  show('review',['READY_FOR_REVIEW','FAILED_VALIDATION'].includes(job.status));
  document.getElementById('approve').disabled=job.status!=='READY_FOR_REVIEW';
  show('download',job.status==='APPROVED_FINAL');
  if(!terminal.has(job.status)&&job.status!=='NEEDS_INPUT')setTimeout(refresh,2000);
}

document.getElementById('answers-form').onsubmit=async event=>{
  event.preventDefault();
  const form=new FormData(event.target);
  const answers=[];
  for(const [id,value] of form.entries()){
    if(id.startsWith('q-'))answers.push({question_id:id,value,comment:document.querySelector(`[data-comment="${CSS.escape(id)}"]`).value,confirmed_by:currentJob.operator_name});
  }
  await api(`/api/jobs/${jobId}/answers`,{method:'POST',body:JSON.stringify({answers})});
  refresh();
};

document.getElementById('approve').onclick=async()=>{
  await api(`/api/jobs/${jobId}/review`,{method:'POST',body:JSON.stringify({action:'approve',corrections:[]})});
  refresh();
};
document.getElementById('revision-btn').onclick=()=>show('revision-form',true);
document.getElementById('revision-form').onsubmit=async event=>{
  event.preventDefault();
  const correction=Object.fromEntries(new FormData(event.target));
  await api(`/api/jobs/${jobId}/review`,{method:'POST',body:JSON.stringify({action:'request_revision',corrections:[correction]})});
  show('revision-form',false);
  refresh();
};

refresh().catch(error=>{document.getElementById('summary').textContent=error.message;});
