const API_BASE = window.WISHNEST_API_BASE || '';
const $ = id => document.getElementById(id);
const priorities = ['Must Have', 'Would Love', 'Nice to Have'];
const money = n => n == null ? 'Not set' : new Intl.NumberFormat('en-US', {style:'currency',currency:'USD'}).format(n);
let parentRenderSequence = 0, childRenderSequence = 0, parentCategories = [], requests = [];
let token = '', role = '', generation = 0, childData = null, catalog = [], giftFilter = 'all', editingProfile = null;
function el(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
}
async function api(path, data) {
  const requestToken = token;
  const response = await fetch(API_BASE + '/api/' + path, {method:data === undefined ? 'GET' : 'POST',
    headers:{'Content-Type':'application/json', Authorization:'Bearer ' + requestToken},
    body:data === undefined ? undefined : JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) {
    if (response.status === 401 && token && token === requestToken) clearSession();
    throw Error(result.error);
  }
  return result;
}
function toast(message) {
  $('toast').textContent = message;
  setTimeout(() => { $('toast').textContent = ''; }, 6000);
}
function button(label, action, cls) {
  const node = el('button', label, cls);
  node.type = 'button';
  node.onclick = async () => {
    node.disabled = true;
    try { await action(); } catch (e) { toast(e.message); }
    finally { node.disabled = false; }
  };
  return node;
}
function empty(container, message) { container.append(el('p', message, 'empty')); }
function clearSession() {
  generation++;
  token = ''; role = ''; childData = null; catalog = []; requests = []; parentCategories = [];
  for (const id of ['profiles','parentCards','parentCatalog','integrationStatus','kidCards','kidCatalog','budgetSummary','purchaseSummary','wishRequests']) $(id).replaceChildren();
  $('issuedCode').textContent = ''; $('codePanel').hidden = true;
  $('kidView').hidden = true; $('parentView').hidden = true; $('entry').hidden = false; $('logout').hidden = true;
  $('profileForm').reset(); $('wishForm').reset(); $('importForm').reset(); $('childCode').value = ''; $('pin').value = '';
  for (const dialog of document.querySelectorAll('dialog[open]')) dialog.close();
}
async function signOut() {
  const previous = token;
  clearSession();
  if (previous) await fetch(API_BASE + '/api/logout', {method:'POST', headers:{'Content-Type':'application/json', Authorization:'Bearer ' + previous}, body:'{}'});
}
function showRole() {
  $('entry').hidden = true; $('logout').hidden = false;
  $('kidView').hidden = role !== 'child'; $('parentView').hidden = role !== 'parent';
  $('kidTab').classList.toggle('active', role === 'child'); $('parentTab').classList.toggle('active', role === 'parent');
}
function offersView(product) {
  const box = el('div', undefined, 'offers');
  for (const offer of product.offers) {
    const row = el('div', undefined, 'offer');
    row.append(el('strong', {'amazon.com':'Amazon','walmart.com':'Walmart','target.com':'Target'}[offer.retailer] || offer.retailer));
    if ('price' in offer) {
      row.append(el('span', money(offer.price)));
      row.append(el('small', offer.source === 'sample' ? 'Illustrative price · not a live offer' : offer.observed_at + ' UTC · ' + offer.source, 'muted'));
    }
    if (offer.url) {
      const a = el('a', role === 'parent' ? 'View product ↗' : 'Browse with permission ↗', 'store-link');
      a.href = offer.url; a.target = '_blank'; a.rel = 'noopener noreferrer' + (offer.affiliate ? ' sponsored' : ''); a.referrerPolicy = 'no-referrer';
      if (role === 'child') a.onclick = e => { if (!confirm('This opens an external store. Follow your parent’s browsing rules. Shopping and payment happen outside this app. Continue?')) e.preventDefault(); };
      row.append(a, el('small', offer.disclosure, 'footnote'));
    }
    box.append(row);
  }
  if (!product.offers.length) box.append(el('p', 'No retailer offers recorded yet.', 'muted'));
  return box;
}
function baseCard(name, subtitle, product=null) {
  const card = el('article', undefined, 'card');
  const art = el('div', undefined, 'toy-art');
  const image = el('img'); image.src = product?.image || '/images/gift.svg'; image.alt = product ? 'Illustration of ' + product.name : 'Gift illustration'; image.loading = 'lazy';
  art.append(image);
  const body = el('div', undefined, 'card-body'); body.append(el('div', subtitle, 'eyebrow'), el('h3', name));
  if (product) {
    body.append(el('p', product.source_label, product.source_kind === 'sample' ? 'sample-label' : 'muted'));
    if (product.content_rating) body.append(el('p', 'ESRB ' + product.content_rating + (product.rating_verified ? ' · verified source' : ' · unverified' + (product.source_kind === 'sample' ? ' sample rating' : ' manual rating')), 'rating-label'));
    if (product.recommendation) body.append(el('p', product.recommendation,'muted'));
  } card.append(art, body);
  return [card, body];
}
function prioritySelect(current, change) {
  const select = el('select'); select.setAttribute('aria-label', 'Gift priority');
  for (const priority of priorities) { const option = el('option', priority); option.value = priority; option.selected = priority === current; select.append(option); }
  select.onchange = async () => { try { await change(select.value); } catch (e) { select.value = current; toast(e.message); } };
  return select;
}
function childWishCard(wish) {
  const [card, body] = baseCard(wish.name, childData.profile.nickname + '’s wish', wish.product);
  body.append(prioritySelect(wish.priority, async priority => { await api('priority', {id:wish.id, priority}); await loadChild(); }));
  if ('value' in wish) body.append(el('p', 'List value: ' + money(wish.value), 'price'));
  body.append(offersView(wish.product));
  return card;
}
function renderCatalog() {
  const query = $('catalogSearch').value.toLowerCase();
  const category = $('categoryFilter').value;
  const products = catalog.filter(p => (p.name + ' ' + p.category).toLowerCase().includes(query) && (!category || p.category === category));
  $('kidCatalog').replaceChildren();
  const wished = new Set(childData.wishes.map(w => w.product.id));
  const requested = new Set(requests.map(r => r.product_id));
  for (const product of products) {
    const [card, body] = baseCard(product.name, product.category, product);
    body.append(offersView(product));
    const add = button(wished.has(product.id) ? 'On My Wish List ✓' : requested.has(product.id) ? 'Request sent to parent' : 'Add to My Wish List', async () => {
      const result = await api('wishes', {product_id:product.id, priority:'Would Love'}); await loadChild();
      toast(result.approval === 'pending' ? 'Request sent. A parent will review it before it joins your list.' : 'Added to your wish list.');
    }, 'primary add-to-list');
    add.disabled = wished.has(product.id) || requested.has(product.id); body.append(add); $('kidCatalog').append(card);
  }
  if (!products.length) empty($('kidCatalog'), 'No matching products. Add a wish idea, or ask a parent to add retailer offers.');
}
async function loadChild() {
  const version = generation, request = ++childRenderSequence;
  const [data, products, wishRequests] = await Promise.all([api('wishes'), api('catalog'), api('requests')]);
  if (version !== generation || request !== childRenderSequence || role !== 'child') return;
  childData = data; catalog = products; requests = wishRequests; showRole();
  $('requestSection').hidden = !requests.length;
  $('wishRequests').replaceChildren(...requests.map(r => el('p',r.name + ' · ' + (r.approval === 'pending' ? 'Waiting for approval' : 'Not approved'), 'request-item')));
  const selectedCategory = $('categoryFilter').value;
  $('categoryFilter').replaceChildren(el('option','All categories')); $('categoryFilter').firstChild.value = '';
  for (const category of [...new Set(products.map(p => p.category))].sort()) { const option = el('option',category); option.value = category; $('categoryFilter').append(option); }
  $('categoryFilter').value = selectedCategory;
  $('childNickname').textContent = data.profile.nickname + '’S CHRISTMAS'; $('count').textContent = data.wishes.length;
  $('budgetSummary').replaceChildren();
  if (data.summary) {
    const summary = data.summary;
    $('budgetSummary').append(el('div', 'Wish-list value', 'eyebrow'), el('strong', money(summary.total)));
    if ('budget' in summary) {
      $('budgetSummary').append(el('span', 'Budget: ' + money(summary.budget)), el('span', summary.remaining == null ? 'No limit set' : summary.remaining < 0 ? money(-summary.remaining) + ' over budget' : money(summary.remaining) + ' remaining'));
    }
    $('budgetSummary').append(el('small', summary.unpriced_items ? summary.unpriced_items + ' unpriced item(s). Total and remaining amount use known prices only.' : 'One of each wish, using its lowest recorded retailer price. Prices may change.', 'muted'));
    if (summary.sample_items) $('budgetSummary').append(el('small', summary.sample_items + ' sample item(s) included at illustrative prices—not live retailer prices.', 'sample-label'));
  } else {
    if ('budget' in data.profile) $('budgetSummary').append(el('strong', 'Budget: ' + money(data.profile.budget)));
    $('budgetSummary').append(el('p', 'Enjoy making your list. Prices are hidden by your parent’s settings.', 'muted'));
  }
  const ordered = [...data.wishes].sort((a,b) => priorities.indexOf(a.priority) - priorities.indexOf(b.priority));
  $('kidCards').replaceChildren(...ordered.map(childWishCard));
  if (!ordered.length) empty($('kidCards'), 'Dream it, wish it. Add an idea or explore the family catalog below.');
  $('browseHint').textContent = data.profile.permissions.links ? 'Compare recorded offers below. External browsing is enabled by your parent. There is no checkout in this app.' : 'Compare products in your family catalog. Your parent has turned external retailer links off.';
  renderCatalog();
}
function privateInput(wish, field, label) {
  const form = el('form', undefined, 'inline-form');
  const input = el('input'); input.type = 'number'; input.min = '0'; input.max = '100000'; input.step = '.01'; input.value = wish[field] ?? ''; input.placeholder = 'Not recorded';
  const wrapper = el('label', label); wrapper.append(input); form.append(wrapper, el('button', 'Save'));
  form.onsubmit = async e => { e.preventDefault(); try { await api('update', {id:wish.id, [field]:input.value}); await loadParent(); } catch (err) { toast(err.message); } };
  return form;
}
function parentWishCard(wish) {
  const [card, body] = baseCard(wish.name, wish.nickname + ' · ' + wish.priority, wish.product);
  body.append(el('p', (wish.purchased ? 'Purchased' : 'Not purchased') + (wish.reserved ? ' · Reserved' : ''), 'badge'), el('p', 'Current list value: ' + money(wish.value)));
  body.append(offersView(wish.product));
  if (wish.review_state !== 'approved') {
    body.append(el('p','Wish approval: ' + wish.review_state,'badge'), button('Approve wish',async () => { await api('update',{id:wish.id,review_state:'approved'}); await loadParent(); },'primary'), button('Decline wish',async () => { await api('update',{id:wish.id,review_state:'declined'}); await loadParent(); }));
    return card;
  }
  const controls = el('div', undefined, 'parent-controls');
  for (const [field,label] of [['purchased', wish.purchased ? 'Undo purchased' : 'Mark purchased'], ['reserved', wish.reserved ? 'Release reservation' : 'Reserve gift']]) {
    controls.append(button(label, async () => { await api('update', {id:wish.id, [field]:!wish[field]}); await loadParent(); }));
  }
  controls.append(privateInput(wish, 'actual_paid', 'Actual paid (private, USD)'), privateInput(wish, 'reference_price', 'Savings baseline (private, USD)'), privateInput(wish, 'target', 'Private target (USD)'));
  body.append(controls, el('p', 'Savings vs. saved baseline: ' + money(wish.savings), 'muted'));
  if (wish.target != null && wish.value != null && wish.value <= wish.target) body.append(el('p', 'Recorded price meets your private target', 'badge'));
  return card;
}
function issueCode(code) { $('issuedCode').textContent = code; $('codePanel').hidden = false; $('codePanel').scrollIntoView({behavior:'smooth', block:'center'}); }
function openProfile(profile=null) {
  editingProfile = profile;
  $('profileForm').reset(); $('profileError').textContent = ''; $('preset').value = 'custom';
  $('profileTitle').textContent = profile ? 'Edit ' + profile.nickname + '’s permissions' : 'Create child profile';
  const categories = [...new Set([...parentCategories, ...(profile?.allowed_categories || []), 'Family Finds'])].sort();
  $('allowedCategories').replaceChildren(...categories.map(category => { const option = el('option',category); option.value = category; option.selected = profile?.allowed_categories?.includes(category) || false; return option; }));
  $('allCategories').checked = profile?.allowed_categories == null; $('allowedCategories').disabled = $('allCategories').checked;
  $('advancedControls').open = false;
  if (profile) {
    const form = $('profileForm'); form.elements.nickname.value = profile.nickname; form.elements.budget.value = profile.budget ?? '';
    for (const key of ['show_prices','show_budget','show_links','use_age_recommendations','allow_unverified_games','require_approval']) form.elements[key].checked = profile[key];
    form.elements.child_age.value = profile.child_age ?? '';
    for (const input of document.querySelectorAll('#ratingPermissions input')) input.checked = profile.allowed_ratings.includes(input.value);
  }
  $('profileDialog').showModal();
}
function profileCard(profile) {
  const [card, body] = baseCard(profile.nickname, 'PARENT-CONTROLLED PROFILE');
  for (const [key,label] of [['show_prices','Prices & total'],['show_budget','Budget'],['show_links','Retailer links']]) body.append(el('p', label + ': ' + (profile[key] ? 'On' : 'Off'), 'muted'));
  body.append(el('p', 'Budget limit: ' + money(profile.budget)));
  body.append(button('Edit permissions & budget', () => openProfile(profile)), button('Generate new access code', async () => { if (confirm('Replace this profile’s code and sign out its active sessions?')) issueCode((await api('profile-code', {id:profile.id})).code); }));
  return card;
}
function offerEditor(product, offer=null) {
  const form = el('form', undefined, 'offer-editor');
  const title = el('label', offer ? 'Update ' + offer.retailer + ' offer' : 'Add Amazon, Walmart, or Target offer');
  const url = el('input'); url.type = 'url'; url.required = true; url.placeholder = 'Direct HTTPS product link'; url.value = offer?.url ?? ''; title.append(url);
  const priceLabel = el('label', 'Displayed product price (USD)'); const price = el('input'); price.type = 'number'; price.min = '0'; price.max = '100000'; price.step = '.01'; price.placeholder = 'Unknown'; price.value = offer?.price ?? ''; priceLabel.append(price);
  form.append(title, priceLabel, el('button', 'Save public offer'));
  form.onsubmit = async e => { e.preventDefault(); try { await api('offers', {product_id:product.id,url:url.value,price:price.value}); await loadParent(); } catch (err) { toast(err.message); } };
  return form;
}
function productMetadataEditor(product) {
  const details = el('details'); details.append(el('summary','Category & rating (manual, unverified)'));
  const form = el('form');
  const fields = {};
  for (const [key,label,value] of [['category','Category',product.category],['recommended_age_min','Suggested minimum age (optional)',product.recommended_age_min ?? '']]) {
    const wrapper = el('label',label), input = el('input'); input.value = value; input.type = key === 'category' ? 'text' : 'number';
    if(key === 'category') { input.required = true; input.maxLength = 80; } else { input.min = '0'; input.max = '18'; input.step = '1'; }
    wrapper.append(input); fields[key] = input; form.append(wrapper);
  }
  for (const [key,label,values,current] of [['media_type','Product kind',['general','video_game'],product.media_type],['content_rating','Self-entered ESRB rating',['','E','E10+','T','M','UNRATED'],product.content_rating ?? '']]) {
    const wrapper = el('label',label), select = el('select');
    for(const value of values) { const option = el('option',value || 'No rating'); option.value = value; option.selected = value === current; select.append(option); }
    wrapper.append(select); fields[key] = select; form.append(wrapper);
  }
  form.append(el('p','Manual ratings are never marked verified. Mandatory eligibility restrictions cannot be edited here.','footnote'),el('button','Save category & rating'));
  form.onsubmit = async e => { e.preventDefault(); const data={id:product.id}; for(const [key,input] of Object.entries(fields)) data[key] = key === 'recommended_age_min' ? input.value === '' ? null : Number(input.value) : input.value; try { await api('product-settings',data); await loadParent(); } catch(error) { toast(error.message); } };
  details.append(form); return details;
}
function parentProductCard(product) {
  const [card, body] = baseCard(product.name, product.category, product); body.append(offersView(product));
  // Use clean product URLs when editing; parent affiliate destinations may differ.
  if (product.source_kind === 'sample') { body.append(el('p','Demo only. No retailer checkout or price editing for sample products.','footnote')); return card; }
  if(product.mandatory_restriction) body.append(el('p','Unavailable to children under mandatory eligibility/app-safety rules.','notice'));
  body.append(productMetadataEditor(product));
  for (const offer of product.offers) body.append(offerEditor(product, {...offer, url:offer.product_url ?? offer.url}));
  if (product.offers.length < 3) body.append(offerEditor(product));
  return card;
}
async function loadParent() {
  const version = generation, request = ++parentRenderSequence;
  const [privacy, profiles, wishes, products, integrations] = await Promise.all([api('privacy'), api('profiles'), api('parent'), api('parent/catalog'), api('integrations')]);
  if (version !== generation || request !== parentRenderSequence || role !== 'parent') return;
  showRole();
  $('integrationStatus').replaceChildren(...integrations.map(i => el('p', i.retailer + ': not connected — ' + i.reason, 'muted')));
  if (pendingShare) { $('importForm').elements.url.value = pendingShare; $('importPanel').open = true; pendingShare = ''; toast('Shared link ready for parent review. Nothing has been imported yet.'); }
  $('consentCheck').checked = privacy.consented; $('consentStatus').textContent = privacy.consented ? 'Permission recorded for ' + privacy.version + '.' : 'Grant permission before creating profiles or enabling child access.';
  $('privacyPanel').open = !privacy.consented; $('newProfile').disabled = !privacy.consented;
  $('profiles').replaceChildren(...profiles.map(profileCard)); if (!profiles.length) empty($('profiles'), 'Create a profile and privately share its access code.');
  parentCategories = [...new Set(products.map(p => p.category))];
  const filtered = wishes.filter(w => giftFilter === 'all' || (giftFilter === 'requests' ? w.review_state !== 'approved' : w.review_state === 'approved' && (giftFilter === 'purchased' ? w.purchased : giftFilter === 'reserved' ? w.reserved && !w.purchased : !w.purchased && !w.reserved)));
  $('parentCards').replaceChildren(...filtered.map(parentWishCard)); if (!filtered.length) empty($('parentCards'), 'No gifts in this view yet.');
  const paid = wishes.reduce((sum,w) => sum + (w.actual_paid ?? 0), 0);
  const savings = wishes.reduce((sum,w) => sum + (w.savings ?? 0), 0);
  $('purchaseSummary').replaceChildren(el('strong', 'Recorded actual paid: ' + money(paid)), el('span', 'Recorded savings: ' + money(savings)), el('small', 'Private totals. Savings use saved baselines, not current price predictions.', 'muted'));
  $('parentCatalog').replaceChildren(...products.map(parentProductCard)); if (!products.length) empty($('parentCatalog'), 'Add a product with retailer offers for children to explore.');
  for (const [id, filter] of [['allGifts','all'],['requestsTab','requests'],['todo','todo'],['reserved','reserved'],['done','purchased']]) $(id).classList.toggle('active', giftFilter === filter);
}
$('childLogin').onsubmit = async e => {
  e.preventDefault(); $('childLoginError').textContent = '';
  try { const result = await api('child-login', {code:$('childCode').value.trim()}); token = result.token; role = 'child'; generation++; $('childCode').value = ''; await loadChild(); }
  catch (err) { $('childLoginError').textContent = err.message; }
};
$('parentTab').onclick = async () => {
  if (role === 'parent') return;
  try { const status = await api('status'); $('loginHint').textContent = status.configured ? 'Unlock your private planning space.' : 'Adult setup: choose a private passphrase of at least eight characters before child use.'; $('pin').value = ''; $('loginError').textContent = ''; $('loginDialog').showModal(); }
  catch (err) { toast(err.message); }
};
$('loginForm').onsubmit = async e => {
  e.preventDefault();
  try {
    const result = await api('unlock', {pin:$('pin').value});
    await signOut(); token = result.token; role = 'parent'; generation++; $('pin').value = ''; $('loginDialog').close(); await loadParent();
  } catch (err) { $('loginError').textContent = err.message; }
};
$('kidTab').onclick = async () => { if (role === 'parent') await signOut(); else if (role === 'child') await loadChild().catch(e => toast(e.message)); };
$('logout').onclick = () => signOut().catch(e => toast(e.message)); $('lockButton').onclick = $('logout').onclick;
$('consentButton').onclick = async () => { try { if (!$('consentCheck').checked) throw Error('Check the permission box first.'); await api('consent', {accepted:true}); await loadParent(); } catch (err) { toast(err.message); } };
$('deleteFamily').onclick = async () => { if (confirm('Delete all child profiles, wishes, products, prices, purchase records, and permission? Your parent passphrase is retained.')) { try { await api('delete-family', {confirmation:'DELETE'}); $('issuedCode').textContent = ''; $('codePanel').hidden = true; await loadParent(); } catch (e) { toast(e.message); } } };
$('newProfile').onclick = () => openProfile(); $('cancelProfile').onclick = () => $('profileDialog').close();
$('profileForm').onsubmit = async e => {
  e.preventDefault(); const form = e.target;
  const data = {nickname:form.elements.nickname.value, budget:form.elements.budget.value};
  for (const key of ['show_prices','show_budget','show_links','use_age_recommendations','allow_unverified_games','require_approval']) data[key] = form.elements[key].checked;
  data.child_age = form.elements.child_age.value === '' ? null : Number(form.elements.child_age.value);
  data.allowed_categories = $('allCategories').checked ? null : Array.from($('allowedCategories').selectedOptions).map(o => o.value);
  data.allowed_ratings = Array.from(document.querySelectorAll('#ratingPermissions input:checked')).map(input => input.value);
  if (editingProfile) data.id = editingProfile.id;
  try { const result = await api('profiles', data); $('profileDialog').close(); await loadParent(); if (result.code) issueCode(result.code); }
  catch (err) { $('profileError').textContent = err.message; }
};
$('preset').onchange = () => {
  const preset = $('preset').value, form = $('profileForm'); if (preset === 'custom') return;
  form.elements.show_prices.checked = preset !== 'guided'; form.elements.show_budget.checked = preset !== 'guided'; form.elements.show_links.checked = preset === 'explorer';
};
$('profileForm').elements.show_prices.onchange = () => { $('preset').value = 'custom'; };
$('profileForm').elements.show_budget.onchange = () => { $('preset').value = 'custom'; };
$('dismissCode').onclick = () => { $('issuedCode').textContent = ''; $('codePanel').hidden = true; };
$('productForm').onsubmit = async e => { e.preventDefault(); try { await api('products', {name:e.target.elements.name.value}); e.target.reset(); await loadParent(); } catch (err) { toast(err.message); } };
$('catalogSearch').oninput = renderCatalog;
$('addButton').onclick = () => { $('wishError').textContent = ''; $('wishDialog').showModal(); };
$('wishForm').onsubmit = async e => { e.preventDefault(); try { const result = await api('wishes', Object.fromEntries(new FormData(e.target))); e.target.reset(); $('wishDialog').close(); await loadChild(); if(result.approval === 'pending') toast('Sent to your parent for approval.'); } catch (err) { $('wishError').textContent = err.message; } };
$('cancelWish').onclick = () => $('wishDialog').close(); $('cancelLogin').onclick = () => $('loginDialog').close();
for (const [id,filter] of [['allGifts','all'],['requestsTab','requests'],['todo','todo'],['reserved','reserved'],['done','purchased']]) $(id).onclick = () => { giftFilter = filter; loadParent().catch(e => toast(e.message)); };
// Refresh public prices and permission changes without deriving anything from purchase status.
setInterval(() => { if (role === 'child' && !document.hidden) loadChild().catch(e => { clearSession(); toast(e.message); }); }, 30000);

$('categoryFilter').onchange = renderCatalog;
$('jumpToList').onclick = () => $('myListHeading').scrollIntoView({behavior:'smooth',block:'start'});
$('importForm').onsubmit = async e => {
  e.preventDefault(); $('importError').textContent = '';
  try { await api('import-link', Object.fromEntries(new FormData(e.target))); e.target.reset(); await loadParent(); toast('Product added to the catalog. No retailer data was fetched.'); }
  catch (error) { $('importError').textContent = error.message; }
};
// Optional web Share Target: untrusted input, kept only in memory until a parent reviews it.
let pendingShare = '';
if (location.pathname === '/share') {
  const params = new URLSearchParams(location.search);
  const input = params.get('url') || params.get('text') || '';
  pendingShare = (input.match(/https:\/\/[^\s]+/) || [''])[0].slice(0,2000);
  history.replaceState(null, '', '/');
  if (pendingShare) toast('Ask a parent to review your shared product in Parent corner.');
}
if ('serviceWorker' in navigator && !window.WISHNEST_NATIVE_BUILD) navigator.serviceWorker.register('/sw.js').catch(() => {});

$('allCategories').onchange = () => { $('allowedCategories').disabled = $('allCategories').checked; };
$('applyAgeDefaults').onclick = () => {
  const form = $('profileForm'), raw = form.elements.child_age.value;
  const age = raw === '' ? null : Number(raw);
  if (age !== null && (!Number.isInteger(age) || age < 0 || age > 17)) return toast('Enter an age from 0 to 17 or leave it blank.');
  form.elements.show_prices.checked = age !== null && age >= 10;
  form.elements.show_budget.checked = age !== null && age >= 10;
  form.elements.show_links.checked = false;
  form.elements.require_approval.checked = age === null || age < 13;
  const allowed = age === null ? ['E','E10+'] : ['E', ...(age>=10 ? ['E10+'] : []), ...(age>=13 ? ['T'] : []), ...(age>=17 ? ['M'] : [])];
  for (const input of document.querySelectorAll('#ratingPermissions input')) input.checked = allowed.includes(input.value);
  $('ageSuggestion').textContent = 'Suggestions applied. Customize any setting before saving. Age does not block products by itself.';
};
if (window.WISHNEST_NATIVE_SCAFFOLD) {
  $('entry').replaceChildren(el('h2','WishNest mobile preview'),el('p','This platform scaffold is not connected to a family server yet. A configured HTTPS backend and a signed native build are needed before device use.'));
  $('parentTab').disabled = true;
}
