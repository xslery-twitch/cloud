const $ = (id) => document.getElementById(id);

/* ---------------- أدوات عامة ---------------- */

async function safeJson(res){
  const text = await res.text();
  try{ return JSON.parse(text); }
  catch(e){
    const snippet = text.slice(0, 120).replace(/\s+/g,' ').trim();
    throw new Error(`رد غير متوقع من السيرفر (كود ${res.status}): ${snippet || 'فارغ'}`);
  }
}

function toast(msg, type='success'){
  const el = document.createElement('div');
  el.className = 'toast ' + type;
  el.innerText = msg;
  $('toastHolder').appendChild(el);
  setTimeout(()=>{ el.style.opacity='0'; el.style.transition='opacity .3s'; setTimeout(()=>el.remove(), 300); }, 3500);
}

/* ---------------- الثيم (فاتح/غامق) ---------------- */

function initTheme(){
  const saved = localStorage.getItem('theme') || 'dark';
  document.documentElement.setAttribute('data-theme', saved);
  $('themeToggle').innerText = saved === 'dark' ? '🌙' : '☀️';
}
$('themeToggle')?.addEventListener('click', ()=>{
  const cur = document.documentElement.getAttribute('data-theme');
  const next = cur === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  $('themeToggle').innerText = next === 'dark' ? '🌙' : '☀️';
});
initTheme();

/* ---------------- التبويبات ---------------- */

document.querySelectorAll('.tab-btn').forEach(btn=>{
  btn.onclick = ()=>{
    document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active'));
    btn.classList.add('active');
    $('panel-' + btn.dataset.tab).classList.add('active');
    if(btn.dataset.tab === 'history') loadFiles();
    if(btn.dataset.tab === 'stats') loadStats();
    if(btn.dataset.tab === 'settings') loadCookieStatus();
  };
});

/* ---------------- الأزرار المتعددة (pills) ---------------- */

function setupPills(containerId, onChange){
  document.querySelectorAll('#'+containerId+' .pill').forEach(p=>{
    p.onclick = ()=>{
      document.querySelectorAll('#'+containerId+' .pill').forEach(x=>x.classList.remove('active'));
      p.classList.add('active');
      onChange(p.dataset.val);
    };
  });
}
function activeVal(containerId){
  return document.querySelector('#'+containerId+' .pill.active').dataset.val;
}
setupPills('typePills', v=>{ $('audioWrap').style.display = v==='audio' ? 'none' : 'block'; });
setupPills('audioPills', ()=>{});
setupPills('durationPills', v=>{ $('rangeFields').style.display = v==='custom' ? 'grid' : 'none'; });

/* ---------------- جلب المعلومات ---------------- */

$('fetchBtn').onclick = async ()=>{
  const url = $('url').value.trim();
  $('infoError').style.display = 'none';
  if(!url){ toast('الصق رابط المقطع أولاً', 'error'); return; }
  $('fetchBtn').disabled = true;
  $('fetchBtn').innerText = 'جاري الجلب...';
  try{
    const res = await fetch('/api/info', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({url})
    });
    const data = await safeJson(res);
    if(!res.ok){ throw new Error(data.error || 'خطأ غير معروف'); }
    $('metaTitle').innerText = data.title;
    $('metaSub').innerText = `المدة: ${data.duration_txt || 'غير معروفة'} · الناشر: ${data.uploader || '—'}`;
    if(data.thumbnail){ $('thumb').src = data.thumbnail; }
    $('infoBox').style.display = 'flex';
    $('optionsCard').style.display = 'block';
    toast('تم جلب المعلومات بنجاح');
  }catch(e){
    $('infoError').innerText = 'تعذّر جلب المعلومات: ' + e.message;
    $('infoError').style.display = 'block';
    toast(e.message, 'error');
  }finally{
    $('fetchBtn').disabled = false;
    $('fetchBtn').innerText = 'جلب معلومات المقطع';
  }
};

/* ---------------- التحميل ---------------- */

$('downloadBtn').onclick = async ()=>{
  const url = $('url').value.trim();
  if(!url) return;
  const file_type = activeVal('typePills');
  const with_audio = activeVal('audioPills') === 'with';
  const quality = parseInt($('quality').value, 10);
  const use_range = activeVal('durationPills') === 'custom';
  const start_sec = use_range ? parseFloat($('startSec').value || 0) : null;
  const end_sec = use_range ? parseFloat($('endSec').value || 0) : null;

  if(use_range && end_sec <= start_sec){
    toast('وقت النهاية يجب أن يكون بعد البداية', 'error');
    return;
  }

  $('downloadBtn').disabled = true;
  $('downloadError').style.display = 'none';
  $('progressWrap').style.display = 'block';
  $('progressBar').style.width = '0%';
  $('statusLine').innerText = 'جاري بدء التحميل...';

  try{
    const res = await fetch('/api/download', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({url, file_type, with_audio, quality, use_range, start_sec, end_sec})
    });
    const data = await safeJson(res);
    if(!res.ok){ throw new Error(data.error || 'تعذّر بدء التحميل'); }
    pollProgress(data.job_id);
  }catch(e){
    showDownloadError(e.message);
  }
};

function showDownloadError(msg){
  $('downloadError').innerText = msg;
  $('downloadError').style.display = 'block';
  $('downloadBtn').disabled = false;
  toast(msg, 'error');
}

function pollProgress(jobId){
  const timer = setInterval(async ()=>{
    try{
      const res = await fetch('/api/progress/'+jobId);
      const job = await safeJson(res);
      $('progressBar').style.width = (job.pct || 0) + '%';
      $('statusLine').innerText = `${job.pct || 0}%  ${job.speed || ''}`;

      if(job.status === 'done'){
        clearInterval(timer);
        $('statusLine').innerText = 'اكتمل التحميل ✓';
        $('downloadBtn').disabled = false;
        toast('اكتمل التحميل بنجاح ✓');
        if(job.filename) playFile(job.filename);
      } else if(job.status === 'error'){
        clearInterval(timer);
        showDownloadError(job.error || 'فشل التحميل');
      }
    }catch(e){
      clearInterval(timer);
      showDownloadError(e.message);
    }
  }, 1000);
}

/* ---------------- المشغل ---------------- */

function playFile(filename){
  const kind = /\.(mp3|m4a)$/i.test(filename) ? 'audio' : 'video';
  const url = '/media/' + encodeURIComponent(filename);
  const holder = $('playerHolder');
  holder.innerHTML = '';
  const el = document.createElement(kind);
  el.src = url;
  el.controls = true;
  el.autoplay = true;
  holder.appendChild(el);
}

/* ---------------- السجل (الملفات) ---------------- */

async function loadFiles(){
  const list = $('fileList');
  try{
    const res = await fetch('/api/files');
    const files = await safeJson(res);
    list.innerHTML = '';
    if(files.length === 0){
      list.innerHTML = '<div class="empty">لا توجد ملفات محمّلة بعد</div>';
      return;
    }
    files.forEach(f=>{
      const row = document.createElement('div');
      row.className = 'file-row';
      const icon = f.kind === 'audio' ? '🎵' : '🎬';
      row.innerHTML = `
        <div class="file-main">
          <div class="file-icon">${icon}</div>
          <div>
            <div class="file-name">${f.name}</div>
            <div class="file-meta">${f.size_mb} MB</div>
          </div>
        </div>
        <button class="file-del" title="حذف">✕</button>`;
      row.querySelector('.file-main').onclick = ()=>{
        playFile(f.name);
        document.querySelector('[data-tab="download"]').click();
      };
      row.querySelector('.file-del').onclick = async (ev)=>{
        ev.stopPropagation();
        try{
          const r = await fetch('/api/files/'+encodeURIComponent(f.name), {method:'DELETE'});
          await safeJson(r);
          toast('تم حذف الملف');
          loadFiles();
        }catch(e){ toast(e.message, 'error'); }
      };
      list.appendChild(row);
    });
  }catch(e){
    list.innerHTML = `<div class="error-box">${e.message}</div>`;
  }
}

/* ---------------- الإحصائيات ---------------- */

async function loadStats(){
  const grid = $('statsGrid');
  try{
    const res = await fetch('/api/stats');
    const s = await safeJson(res);
    const totalMb = (s.total_bytes / 1024 / 1024).toFixed(1);
    grid.innerHTML = `
      <div class="stat-box"><div class="num">${s.total_downloads}</div><div class="label">إجمالي التحميلات</div></div>
      <div class="stat-box"><div class="num">${s.video_count}</div><div class="label">فيديوهات</div></div>
      <div class="stat-box"><div class="num">${s.audio_count}</div><div class="label">ملفات صوت</div></div>
      <div class="stat-box"><div class="num">${totalMb}</div><div class="label">إجمالي الحجم (MB)</div></div>
      <div class="stat-box"><div class="num">${s.failed}</div><div class="label">محاولات فاشلة</div></div>
    `;
  }catch(e){
    grid.innerHTML = `<div class="error-box">${e.message}</div>`;
  }
}

/* ---------------- الكوكيز ---------------- */

async function loadCookieStatus(){
  try{
    const res = await fetch('/api/cookies/status');
    const data = await safeJson(res);
    $('cookieDot').classList.toggle('on', data.has_cookies);
    $('cookieStatusText').innerText = data.has_cookies ? 'ملف كوكيز مرفوع ومفعّل' : 'لا يوجد ملف كوكيز حاليًا';
  }catch(e){
    $('cookieStatusText').innerText = 'تعذّر التحقق: ' + e.message;
  }
}

$('uploadCookieBtn').onclick = async ()=>{
  const file = $('cookieFile').files[0];
  if(!file){ toast('اختر ملف أولاً', 'error'); return; }
  const fd = new FormData();
  fd.append('cookies', file);
  try{
    const res = await fetch('/api/cookies', { method:'POST', body: fd });
    await safeJson(res);
    toast('تم رفع ملف الكوكيز بنجاح');
    loadCookieStatus();
  }catch(e){ toast(e.message, 'error'); }
};

$('removeCookieBtn').onclick = async ()=>{
  try{
    const res = await fetch('/api/cookies', { method:'DELETE' });
    await safeJson(res);
    toast('تمت إزالة ملف الكوكيز');
    loadCookieStatus();
  }catch(e){ toast(e.message, 'error'); }
};
