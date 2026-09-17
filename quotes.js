/* Same-origin snapshots avoid third-party browser access restrictions. */
let quoteSnapshot = null;
let quoteLoadFailed = false;
let quoteRequestPending = false;
const quoteTime = new Intl.DateTimeFormat('zh-TW', {
  timeZone: 'Asia/Taipei', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', hour12: false
});
function quoteElement(tag, className, text) {
  const element = document.createElement(tag);
  element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}
function quoteRow(label, value) {
  const row = quoteElement('span', 'quote-row');
  row.append(quoteElement('span', 'quote-label', label));
  const price = Number.isFinite(value.price) ? '$' + value.price.toLocaleString('en-US', {
    minimumFractionDigits: 2, maximumFractionDigits: 2
  }) : '—';
  row.append(quoteElement('span', 'quote-price', price));
  const percent = value.changePercent;
  const direction = !Number.isFinite(percent) || percent === 0 ? 'flat' : percent > 0 ? 'up' : 'down';
  const change = !Number.isFinite(percent) ? '—' :
    (percent > 0 ? '▲ +' : percent < 0 ? '▼ ' : '') + percent.toFixed(2) + '%';
  row.append(quoteElement('span', 'quote-change ' + direction, change));
  const time = quoteTime.format(new Date(value.time * 1000));
  row.title = label + '行情時間：' + time + '（台北時間）';
  row.append(quoteElement('span', 'quote-time', time));
  return row;
}
window.renderQuotes = function () {
  document.querySelectorAll('#stocks .stock').forEach(button => {
    const symbol = button.querySelector('strong').textContent;
    let container = button.querySelector('.quote');
    if (!container) {
      container = quoteElement('span', 'quote');
      button.append(container);
    }
    container.replaceChildren();
    const quote = quoteSnapshot?.quotes?.[symbol];
    if (!quote?.regular) {
      container.append(quoteElement('span', 'quote-empty', quoteSnapshot || quoteLoadFailed ?
        '行情暫無資料' : '行情載入中…'));
      return;
    }
    container.append(quoteRow(quote.marketState === 'regular' ? '一般' : '收盤', quote.regular));
    for (const [key, label] of [['pre', '盤前'], ['post', '盤後']]) {
      if (quote[key]) container.append(quoteRow(label, quote[key]));
    }
    if (!quote.pre && !quote.post) {
      container.append(quoteElement('span', 'quote-empty', '盤前／盤後：暫無資料'));
    }
    if (quote.status !== 'ok' || Date.now() / 1000 - quote.fetchedAt > 1200) {
      container.append(quoteElement('span', 'quote-warning', '上次行情 · 等待更新'));
    }
  });
  const status = document.getElementById('quote-status');
  if (!status) return;
  status.textContent = quoteSnapshot ?
    '資料擷取：' + quoteTime.format(new Date(quoteSnapshot.generatedAt * 1000)) +
    '（台北時間）' + (quoteLoadFailed ? ' · 更新暫時失敗，保留上次行情' : '') :
    quoteLoadFailed ? '行情暫時無法載入，請稍後重新整理。' : '正在載入所有股票行情…';
};
async function loadQuotes() {
  if (quoteRequestPending) return;
  quoteRequestPending = true;
  const refresh = document.getElementById('refresh-quotes');
  if (refresh) refresh.disabled = true;
  try {
    const response = await fetch('./quotes.json?t=' + Math.floor(Date.now() / 60000), {
      cache: 'no-store', signal: AbortSignal.timeout(15000)
    });
    if (!response.ok) throw new Error('Quotes unavailable');
    const result = await response.json();
    if (!result.quotes || !Number.isFinite(result.generatedAt)) throw new Error('Invalid quotes');
    quoteSnapshot = result;
    quoteLoadFailed = false;
  } catch {
    quoteLoadFailed = true;
  } finally {
    quoteRequestPending = false;
    if (refresh) refresh.disabled = false;
    window.renderQuotes();
  }
}
document.getElementById('refresh-quotes').addEventListener('click', loadQuotes);
document.addEventListener('visibilitychange', () => { if (!document.hidden) loadQuotes(); });
window.renderQuotes();
loadQuotes();
setInterval(() => { if (!document.hidden) loadQuotes(); }, 60000);
