// STP Picks — "ส่งให้ bot" bookmarklet.
// Use: open https://affiliate.shopee.co.th/offer/product_offer (logged in, normal browser), click the bookmark.
// It re-requests the list the page itself shows (5 pages x 20, 1.5-3 s apart) and downloads
// stp-offers-YYYY-MM-DD.json. Nothing is posted anywhere; the file stays on your Mac.
// Install: run `python -m agent bookmarklet` and paste the printed line as the URL of a new bookmark.
(async () => {
  if (!location.host.startsWith('affiliate.shopee')) {
    alert('เปิดหน้า affiliate.shopee.co.th/offer/product_offer ก่อน แล้วกดใหม่');
    return;
  }
  const PAGES = 5, LIMIT = 20;
  let all = [];
  for (let p = 0; p < PAGES; p++) {
    const r = await fetch(`/api/v3/offer/product/list?list_type=0&sort_type=1&page_offset=${p * LIMIT}` +
      `&page_limit=${LIMIT}&client_type=1`, { credentials: 'include' }).then(r => r.json()).catch(() => null);
    if (!r || r.code !== 0 || !r.data) { if (!all.length) { alert('อ่านรายการไม่ได้ (code ' + (r && r.code) + ')'); return; } break; }
    all = all.concat(r.data.list || []);
    if ((r.data.list || []).length < LIMIT) break;
    await new Promise(s => setTimeout(s, 1500 + Math.random() * 1500));
  }
  const blob = new Blob([JSON.stringify({ captured_at: new Date().toISOString(), source: location.href, list: all })],
    { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'stp-offers-' + new Date().toISOString().slice(0, 10) + '.json';
  a.click();
  alert('บันทึก ' + all.length + ' สินค้าแล้ว → ไฟล์ใน Downloads');
})();
