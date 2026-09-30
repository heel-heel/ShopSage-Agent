let token = localStorage.getItem('shopsage_consumer_token');

async function ensureSession() {
  if (token) return token;
  const response = await fetch('/api/auth/consumer', { method: 'POST' });
  const data = await response.json();
  token = data.access_token;
  localStorage.setItem('shopsage_consumer_token', token);
  return token;
}

async function api(path, options = {}) {
  await ensureSession();
  const response = await fetch(path, { ...options, headers: { Authorization: `Bearer ${token}`, ...(options.headers || {}) } });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || '请求未完成，请稍后重试。');
  return data;
}

function escapeHtml(value) { const node = document.createElement('div'); node.textContent = value; return node.innerHTML; }
function categoryName(value) { return ({coffee_bean:'咖啡豆', grinder:'磨豆机', dripper:'滤杯', kettle:'手冲壶', bundle:'组合套装'})[value] || value; }

document.getElementById('decision-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button');
  button.disabled = true; button.querySelector('span').textContent = '正在比对证据…';
  try {
    const budget = Number(document.getElementById('budget').value) || null;
    const data = await api('/api/consumer/chat', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ question:document.getElementById('question').value, budget, brew_method:document.getElementById('brew-method').value || null, experience:document.getElementById('experience').value || null }) });
    renderResult(data);
  } catch (error) { alert(error.message); }
  finally { button.disabled = false; button.querySelector('span').textContent = '生成可信推荐'; }
});

function renderResult(data) {
  document.getElementById('result').hidden = false;
  document.getElementById('answer').textContent = data.answer;
  document.getElementById('trace-badge').textContent = `trace ${data.trace_id.slice(0,8)}`;
  document.getElementById('constraints').innerHTML = [...data.matched_constraints, ...data.unmet_constraints].map(item => `<span class="chip">${escapeHtml(item)}</span>`).join('');
  document.getElementById('recommendations').innerHTML = data.recommendations.map((item, index) => `<article class="recommendation"><div class="product-meta"><span>${categoryName(item.category)}</span><span class="score">匹配 ${item.match_score}</span></div><h3>${escapeHtml(item.name)}</h3><div class="product-meta"><strong>¥${item.price}</strong><span>★ ${item.rating}</span></div><ul class="reason-list">${item.reasons.map(reason => `<li>${escapeHtml(reason)}</li>`).join('')}</ul>${item.tradeoffs.length ? `<ul class="tradeoff-list">${item.tradeoffs.map(tradeoff => `<li>${escapeHtml(tradeoff)}</li>`).join('')}</ul>` : ''}<div class="feedback-row"><button data-event="save" data-product="${item.product_id}">收藏</button><button data-event="not_fit" data-product="${item.product_id}">不适合我</button></div></article>`).join('') || '<p>没有找到符合所有硬条件的商品。请调整预算或冲煮方式后再试。</p>';
  document.getElementById('evidence').innerHTML = data.citations.map(item => `<div class="citation"><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.excerpt)}</p></div>`).join('');
  document.querySelectorAll('[data-event]').forEach(button => button.addEventListener('click', async () => { await api('/api/consumer/events', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({event_type:button.dataset.event,product_id:button.dataset.product})}); button.textContent = button.dataset.event === 'save' ? '已收藏' : '已记录'; button.disabled = true; }));
  document.getElementById('result').scrollIntoView({behavior:'smooth', block:'start'});
}

ensureSession();
