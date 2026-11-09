/**
 * tests/test_harness_dom.js
 * Empirical DOM & Interactive JavaScript Test Harness for Milestone 2.
 * Stress-tests Drag & Drop, Deletion Modal, In-App Preview Modal, Search/Sort/Filter, and XSS Vectors.
 */

const fs = require('fs');
const assert = require('assert');

const appJsPath = '/home/zen/Projects/storista/static/js/app.js';
const appJsCode = fs.readFileSync(appJsPath, 'utf8');

console.log('======================================================================');
console.log('STORISTA EMPIRICAL CHALLENGER — MILESTONE 2 INTERACTIVE DOM HARNESS');
console.log('======================================================================\n');

// Mock DOM Infrastructure
class MockClassList {
  constructor() { this.classes = new Set(); }
  add(...c) { c.forEach(x => this.classes.add(x)); }
  remove(...c) { c.forEach(x => this.classes.delete(x)); }
  toggle(c, force) {
    if (force !== undefined) {
      force ? this.add(c) : this.remove(c);
      return force;
    }
    const has = this.classes.has(c);
    has ? this.remove(c) : this.add(c);
    return !has;
  }
  contains(c) { return this.classes.has(c); }
}

class MockElement {
  constructor(tag = 'div', id = '') {
    this.tagName = tag.toUpperCase();
    this.id = id;
    this.classList = new MockClassList();
    this.dataset = {};
    this.style = {};
    this.children = [];
    this._textContent = '';
    this._innerHTML = '';
    this.listeners = {};
    this.value = '';
    this.disabled = false;
    this.files = [];
    this.src = '';
    this.href = '';
    this.open = false;
    this.boundingBox = { top: 100, left: 100, width: 400, height: 300 };
  }

  get textContent() {
    if (this.children.length === 0) return this._textContent;
    return this.children.map(c => c.textContent).join('');
  }
  set textContent(v) {
    this._textContent = String(v);
    this._innerHTML = String(v)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  get innerHTML() {
    if (this._innerHTML) return this._innerHTML;
    if (this.children.length === 0) return this._textContent;
    return this.children.map(c => c.innerHTML || c.textContent).join('');
  }
  set innerHTML(v) { this._innerHTML = String(v); }

  setAttribute(k, v) { this[k] = String(v); }
  getAttribute(k) { return this[k] !== undefined ? this[k] : null; }

  addEventListener(event, fn) {
    if (!this.listeners[event]) this.listeners[event] = [];
    this.listeners[event].push(fn);
  }

  dispatchEvent(event) {
    const list = this.listeners[event.type] || [];
    for (const fn of list) {
      fn(event);
      if (event._propagationStopped) break;
    }
    // Bubble to parent if applicable
    if (event.bubbles && !event._propagationStopped && this.parentElement) {
      this.parentElement.dispatchEvent(event);
    }
  }

  closest(selector) {
    if (selector.startsWith('.')) {
      const cls = selector.slice(1);
      if (this.classList.contains(cls)) return this;
      if (this.parentElement) return this.parentElement.closest(selector);
    }
    return null;
  }

  appendChild(child) {
    const existingIdx = this.children.indexOf(child);
    if (existingIdx !== -1) {
      this.children.splice(existingIdx, 1);
    }
    child.parentElement = this;
    this.children.push(child);
  }

  removeChild(child) {
    const idx = this.children.indexOf(child);
    if (idx !== -1) this.children.splice(idx, 1);
  }

  querySelector(sel) {
    if (sel.startsWith('.')) {
      const cls = sel.slice(1);
      for (const child of this.children) {
        if (child.classList.contains(cls)) return child;
        const found = child.querySelector(sel);
        if (found) return found;
      }
    }
    return null;
  }

  querySelectorAll(sel) {
    const results = [];
    const walk = (el) => {
      for (const child of el.children) {
        if (sel.startsWith('.')) {
          if (child.classList.contains(sel.slice(1))) results.push(child);
        } else if (sel.startsWith('#')) {
          if (child.id === sel.slice(1)) results.push(child);
        }
        walk(child);
      }
    };
    walk(this);
    return results;
  }

  focus() { this._focused = true; }
  blur() { this._focused = false; }
  select() { this._selected = true; }
  showModal() { this.open = true; }
  close() { this.open = false; }
  getBoundingClientRect() { return this.boundingBox; }
}

class MockEvent {
  constructor(type, init = {}) {
    this.type = type;
    this.bubbles = init.bubbles !== undefined ? init.bubbles : true;
    this.defaultPrevented = false;
    this._propagationStopped = false;
    this.clientX = init.clientX || 0;
    this.clientY = init.clientY || 0;
    this.key = init.key || '';
    this.code = init.code || '';
    this.target = init.target || null;
    this.dataTransfer = init.dataTransfer || null;
  }
  preventDefault() { this.defaultPrevented = true; }
  stopPropagation() { this._propagationStopped = true; }
}

// Build Global DOM Environment
const elementsRegistry = {};
function getOrCreateElement(id, tag = 'div') {
  if (!elementsRegistry[id]) {
    elementsRegistry[id] = new MockElement(tag, id);
  }
  return elementsRegistry[id];
}

const windowListeners = {};
const docListeners = {};

const mockDocument = {
  getElementById: (id) => getOrCreateElement(id),
  querySelectorAll: (sel) => {
    if (sel === '.upload-tabs .tab-btn') {
      return [getOrCreateElement('tab-file-btn', 'button'), getOrCreateElement('tab-url-btn', 'button')];
    }
    if (sel === '.filter-bar .filter-pill') {
      return [
        getOrCreateElement('pill-all', 'button'),
        getOrCreateElement('pill-folder', 'button'),
        getOrCreateElement('pill-document', 'button'),
        getOrCreateElement('pill-image', 'button'),
        getOrCreateElement('pill-media', 'button'),
      ];
    }
    return [];
  },
  addEventListener: (type, fn) => {
    if (!docListeners[type]) docListeners[type] = [];
    docListeners[type].push(fn);
  },
  createElement: (tag) => new MockElement(tag)
};

const mockWindow = {
  addEventListener: (type, fn) => {
    if (!windowListeners[type]) windowListeners[type] = [];
    windowListeners[type].push(fn);
  },
  showToast: null
};

// Set Node Globals
global.window = mockWindow;
global.document = mockDocument;
global.DataTransfer = class {
  constructor() {
    this.items = { add: (f) => this.files.push(f) };
    this.files = [];
  }
};
global.URL = {
  createObjectURL: (b) => 'blob:storista-mock-' + Math.random().toString(36).slice(2),
  revokeObjectURL: (u) => { mockWindow._lastRevokedUrl = u; }
};
global.fetch = async (url, opts) => {
  mockWindow._lastFetchUrl = url;
  mockWindow._lastFetchOpts = opts;
  return {
    ok: true,
    status: 200,
    json: async () => ({ status: 'success' }),
    blob: async () => ({ text: async () => 'sample text content' })
  };
};

// Pre-create standard elements expected by app.js
const dropZone = getOrCreateElement('dropZone');
const fileInput = getOrCreateElement('fileInput', 'input');
const dropText = getOrCreateElement('dropText');
const dropIcon = getOrCreateElement('dropIcon');
const selectedFileInfo = getOrCreateElement('selectedFileInfo');
const selectedFileName = getOrCreateElement('selectedFileName');
const selectedFileSize = getOrCreateElement('selectedFileSize');
const clearFileBtn = getOrCreateElement('clearFileBtn', 'button');
const fileSubmitBtn = getOrCreateElement('fileSubmitBtn', 'button');
const toastContainer = getOrCreateElement('toastContainer');
const deleteModal = getOrCreateElement('deleteModal', 'dialog');
const deleteTargetName = getOrCreateElement('deleteTargetName');
const deleteFolderNotice = getOrCreateElement('deleteFolderNotice');
const cancelDeleteBtn = getOrCreateElement('cancelDeleteBtn', 'button');
const confirmDeleteBtn = getOrCreateElement('confirmDeleteBtn', 'button');
const previewModal = getOrCreateElement('previewModal', 'dialog');
const previewFileName = getOrCreateElement('previewFileName');
const previewFileSize = getOrCreateElement('previewFileSize');
const previewMimeType = getOrCreateElement('previewMimeType');
const previewLoadingState = getOrCreateElement('previewLoadingState');
const previewImagePane = getOrCreateElement('previewImagePane');
const previewImg = getOrCreateElement('previewImg', 'img');
const previewPdfPane = getOrCreateElement('previewPdfPane');
const previewPdfFrame = getOrCreateElement('previewPdfFrame', 'iframe');
const previewTextPane = getOrCreateElement('previewTextPane');
const previewCodeContent = getOrCreateElement('previewCodeContent', 'code');
const previewFallbackPane = getOrCreateElement('previewFallbackPane');
const fileList = getOrCreateElement('file-list');
const searchInput = getOrCreateElement('searchInput', 'input');
const searchClearBtn = getOrCreateElement('searchClearBtn', 'button');
const kbdBadge = getOrCreateElement('search-kbd-badge');
const sortSelect = getOrCreateElement('sortSelect', 'select');
const emptySearchState = getOrCreateElement('search-empty-state');
const searchTermDisplay = getOrCreateElement('search-term-display');
const fileCountDisplay = getOrCreateElement('file-count');
const totalSizeDisplay = getOrCreateElement('total-size');

// Execute app.js in this sandbox
eval(appJsCode);

// Trigger DOMContentLoaded
const domLoadedHandlers = docListeners['DOMContentLoaded'] || [];
domLoadedHandlers.forEach(fn => fn());

console.log('[+] app.js initialized successfully in mock DOM environment.\n');

let passCount = 0;
let failCount = 0;

function runTest(name, fn) {
  try {
    fn();
    console.log(`  ✓ PASS: ${name}`);
    passCount++;
  } catch (err) {
    console.error(`  ✗ FAIL: ${name}`);
    console.error(`    Error: ${err.message}`);
    failCount++;
  }
}

// ============================================================================
// FOCUS 1: Drag-and-Drop Upload Stress Tests
// ============================================================================
console.log('--- Focus 1: Drag-and-Drop Upload ---');

runTest('Dragenter adds drag-active class and updates label', () => {
  const enterEvt = new MockEvent('dragenter');
  dropZone.dispatchEvent(enterEvt);
  assert.strictEqual(dropZone.classList.contains('drag-active'), true, 'dropZone should have drag-active');
  assert.strictEqual(dropText.textContent, 'Release to drop file');
});

runTest('Dragover sets dropEffect to copy', () => {
  const dt = {};
  const overEvt = new MockEvent('dragover', { dataTransfer: dt });
  dropZone.dispatchEvent(overEvt);
  assert.strictEqual(dt.dropEffect, 'copy', 'dropEffect should be set to copy');
  assert.strictEqual(dropZone.classList.contains('drag-active'), true);
});

runTest('Dragleave nested counter decrements without clearing active until zero', () => {
  // We already fired one dragenter above. Fire another (e.g. entering child)
  dropZone.dispatchEvent(new MockEvent('dragenter'));
  // Now dragleave from child
  dropZone.dispatchEvent(new MockEvent('dragleave'));
  assert.strictEqual(dropZone.classList.contains('drag-active'), true, 'Should stay active while counter > 0');

  // Second dragleave (leaving dropZone)
  dropZone.dispatchEvent(new MockEvent('dragleave'));
  assert.strictEqual(dropZone.classList.contains('drag-active'), false, 'Should remove active when counter reaches 0');
  assert.strictEqual(dropText.textContent, 'Click or drag file here');
});

runTest('Drop multiple files selects only first file and handles cleanly', () => {
  const file1 = { name: 'first_file.pdf', size: 1024 * 1024 };
  const file2 = { name: 'second_file.pdf', size: 2 * 1024 * 1024 };
  const dropEvt = new MockEvent('drop', {
    dataTransfer: { files: [file1, file2] }
  });
  dropZone.dispatchEvent(dropEvt);

  assert.strictEqual(dropZone.classList.contains('drag-active'), false, 'Active removed after drop');
  assert.strictEqual(selectedFileName.textContent, 'first_file.pdf', 'Selected first file');
  assert.strictEqual(selectedFileSize.textContent, '1 MB');
  assert.strictEqual(selectedFileInfo.classList.contains('d-none'), false, 'Selected file card visible');
  assert.strictEqual(fileSubmitBtn.disabled, false, 'Submit button enabled');
});

runTest('Drop zero files handles gracefully without crash', () => {
  const dropEvt = new MockEvent('drop', {
    dataTransfer: { files: [] }
  });
  dropZone.dispatchEvent(dropEvt);
  assert.strictEqual(dropZone.classList.contains('drag-active'), false);
  assert.strictEqual(dropText.textContent, 'Click or drag file here');
});

runTest('Drop oversized file (>50MB) rejects and displays danger toast', () => {
  const bigFile = { name: 'huge_video.mp4', size: 60 * 1024 * 1024 }; // 60MB
  const dropEvt = new MockEvent('drop', {
    dataTransfer: { files: [bigFile] }
  });
  dropZone.dispatchEvent(dropEvt);

  assert.strictEqual(selectedFileInfo.classList.contains('d-none'), true, 'File card hidden for oversized file');
  assert.strictEqual(fileSubmitBtn.disabled, true, 'Submit button disabled');
  // Check that toast was created
  assert(toastContainer.children.length > 0, 'Toast container should receive alert');
  const lastToast = toastContainer.children[toastContainer.children.length - 1];
  assert(lastToast.innerHTML.includes('exceeds the 50MB limit'), 'Toast should state 50MB limit');
});

runTest('Drop directory object (size 0) handles without crash', () => {
  const dirObj = { name: 'my_directory', size: 0 };
  const dropEvt = new MockEvent('drop', {
    dataTransfer: { files: [dirObj] }
  });
  dropZone.dispatchEvent(dropEvt);
  assert.strictEqual(selectedFileName.textContent, 'my_directory');
  assert.strictEqual(selectedFileSize.textContent, '0 B');
  assert.strictEqual(fileSubmitBtn.disabled, false);
});

// ============================================================================
// FOCUS 2: Deletion Modal Stress Tests
// ============================================================================
console.log('\n--- Focus 2: Deletion Modal ---');

runTest('Deletion modal opens with special characters & spaces in file path', () => {
  const btn = new MockElement('button');
  btn.classList.add('btn-delete');
  btn.dataset.path = 'storage/documents/my secret (2026) & file.txt';
  btn.dataset.type = 'file';
  btn.dataset.name = 'my secret (2026) & file.txt';

  const clickEvt = new MockEvent('click', { target: btn });
  const clickListeners = docListeners['click'] || [];
  clickListeners.forEach(fn => fn(clickEvt));

  assert.strictEqual(deleteModal.open, true, 'Modal should be open');
  assert.strictEqual(deleteTargetName.textContent, 'my secret (2026) & file.txt', 'Name safely populated via textContent');
  assert.strictEqual(deleteFolderNotice.classList.contains('d-none'), true, 'Folder notice hidden for file');
});

runTest('Deletion modal opens with single quotes and apostrophes in filename', () => {
  const btn = new MockElement('button');
  btn.classList.add('btn-delete');
  btn.dataset.path = "storage/it's a 'special' file.txt";
  btn.dataset.type = 'file';
  btn.dataset.name = "it's a 'special' file.txt";

  const clickEvt = new MockEvent('click', { target: btn });
  (docListeners['click'] || []).forEach(fn => fn(clickEvt));

  assert.strictEqual(deleteModal.open, true);
  assert.strictEqual(deleteTargetName.textContent, "it's a 'special' file.txt");
});

runTest('Deletion modal toggles folder warning notice for directory deletion', () => {
  const btn = new MockElement('button');
  btn.classList.add('btn-delete');
  btn.dataset.path = 'storage/important_folder';
  btn.dataset.type = 'folder';
  btn.dataset.name = 'important_folder';

  const clickEvt = new MockEvent('click', { target: btn });
  (docListeners['click'] || []).forEach(fn => fn(clickEvt));

  assert.strictEqual(deleteModal.open, true);
  assert.strictEqual(deleteFolderNotice.classList.contains('d-none'), false, 'Folder warning should be visible');
});

runTest('Confirm deletion correctly URL-encodes each path segment for DELETE request', async () => {
  // activeDeleteTarget is set from previous test: storage/important_folder
  const confirmListeners = confirmDeleteBtn.listeners['click'] || [];
  assert(confirmListeners.length > 0, 'Confirm delete button should have click listener');
  await confirmListeners[0]();

  assert.strictEqual(mockWindow._lastFetchOpts.method, 'DELETE');
  assert.strictEqual(mockWindow._lastFetchUrl, '/api/folders/storage/important_folder');
});

runTest('Confirm deletion path encoding preserves subfolders while encoding special characters', async () => {
  // Set target with spaces and special chars
  const btn = new MockElement('button');
  btn.classList.add('btn-delete');
  btn.dataset.path = 'storage/folder with spaces/file#1?.txt';
  btn.dataset.type = 'file';
  btn.dataset.name = 'file#1?.txt';
  (docListeners['click'] || []).forEach(fn => fn(new MockEvent('click', { target: btn })));

  const confirmListeners = confirmDeleteBtn.listeners['click'] || [];
  await confirmListeners[0]();

  // Each segment encoded: storage -> storage, folder with spaces -> folder%20with%20spaces, file#1?.txt -> file%231%3F.txt
  assert.strictEqual(mockWindow._lastFetchUrl, '/api/files/storage/folder%20with%20spaces/file%231%3F.txt');
});

runTest('Backdrop click dismissal: clicks outside dialog bounding box close modal', () => {
  deleteModal.open = true;
  // Bounding box is top: 100, left: 100, width: 400, height: 300
  // Click at (50, 50) is OUTSIDE
  const clickOutside = new MockEvent('click', { clientX: 50, clientY: 50 });
  const modalClickListeners = deleteModal.listeners['click'] || [];
  modalClickListeners.forEach(fn => fn(clickOutside));

  assert.strictEqual(deleteModal.open, false, 'Modal should close on outside click');

  // Click at (200, 200) is INSIDE
  deleteModal.open = true;
  const clickInside = new MockEvent('click', { clientX: 200, clientY: 200 });
  modalClickListeners.forEach(fn => fn(clickInside));

  assert.strictEqual(deleteModal.open, true, 'Modal should remain open on inside click');
});

// ============================================================================
// FOCUS 3: In-App Preview Modal Stress & XSS Tests
// ============================================================================
console.log('\n--- Focus 3: In-App Preview Modal ---');

runTest('Preview modal handles text/code files and renders via textContent', async () => {
  const btn = new MockElement('button');
  btn.classList.add('btn-preview');
  btn.dataset.path = 'storage/script.py';
  btn.dataset.name = 'script.py';
  btn.dataset.mime = 'text/x-python';
  btn.dataset.size = '1.2 KB';

  const clickEvt = new MockEvent('click', { target: btn });
  for (const fn of (docListeners['click'] || [])) {
    await fn(clickEvt);
  }

  assert.strictEqual(previewModal.open, true);
  assert.strictEqual(previewFileName.textContent, 'script.py');
  assert.strictEqual(previewTextPane.classList.contains('d-none'), false, 'Text pane should be active');
  assert.strictEqual(previewImagePane.classList.contains('d-none'), true);
  assert.strictEqual(previewPdfPane.classList.contains('d-none'), true);
});

runTest('Preview modal handles SVG files using img element (neutralizing scripts)', async () => {
  const btn = new MockElement('button');
  btn.classList.add('btn-preview');
  btn.dataset.path = 'storage/diagram.svg';
  btn.dataset.name = 'diagram.svg';
  btn.dataset.mime = 'image/svg+xml';
  btn.dataset.size = '4 KB';

  const clickEvt = new MockEvent('click', { target: btn });
  for (const fn of (docListeners['click'] || [])) {
    await fn(clickEvt);
  }

  assert.strictEqual(previewImagePane.classList.contains('d-none'), false, 'Image pane active for SVG');
  assert(previewImg.src.startsWith('blob:'), 'Img src set to blob url');
  assert.strictEqual(previewPdfPane.classList.contains('d-none'), true);
  assert.strictEqual(previewTextPane.classList.contains('d-none'), true);
});

runTest('Preview modal handles PDF files using iframe', async () => {
  const btn = new MockElement('button');
  btn.classList.add('btn-preview');
  btn.dataset.path = 'storage/report.pdf';
  btn.dataset.name = 'report.pdf';
  btn.dataset.mime = 'application/pdf';
  btn.dataset.size = '250 KB';

  const clickEvt = new MockEvent('click', { target: btn });
  for (const fn of (docListeners['click'] || [])) {
    await fn(clickEvt);
  }

  assert.strictEqual(previewPdfPane.classList.contains('d-none'), false, 'PDF pane active');
  assert(previewPdfFrame.src.startsWith('blob:'), 'PDF iframe src set to blob');
});

runTest('Preview modal handles unsupported binary formats via fallback pane', async () => {
  const btn = new MockElement('button');
  btn.classList.add('btn-preview');
  btn.dataset.path = 'storage/archive.zip';
  btn.dataset.name = 'archive.zip';
  btn.dataset.mime = 'application/zip';
  btn.dataset.size = '10 MB';

  const clickEvt = new MockEvent('click', { target: btn });
  for (const fn of (docListeners['click'] || [])) {
    await fn(clickEvt);
  }

  assert.strictEqual(previewFallbackPane.classList.contains('d-none'), false, 'Fallback pane active for unsupported binary');
  assert.strictEqual(previewImagePane.classList.contains('d-none'), true);
  assert.strictEqual(previewTextPane.classList.contains('d-none'), true);
});

runTest('XSS Injection in Preview filename is safely assigned via textContent', async () => {
  const xssName = '<script>alert(1)</script>.txt';
  const btn = new MockElement('button');
  btn.classList.add('btn-preview');
  btn.dataset.path = `storage/${xssName}`;
  btn.dataset.name = xssName;
  btn.dataset.mime = 'text/plain';

  const clickEvt = new MockEvent('click', { target: btn });
  for (const fn of (docListeners['click'] || [])) {
    await fn(clickEvt);
  }

  assert.strictEqual(previewFileName.textContent, xssName);
  // In our mock, textContent sets _textContent literally without parsing HTML tags
  assert.strictEqual(previewFileName._textContent, xssName);
});

// ============================================================================
// FOCUS 4: Search, Sort & Filtering Engine
// ============================================================================
console.log('\n--- Focus 4: Search, Sort & Filtering Engine ---');

// Populate fileList with test items
fileList.children = [];
const testFilesData = [
  { name: 'alpha.txt', isDir: 'false', bytes: '100', cat: 'document' },
  { name: 'beta.png', isDir: 'false', bytes: '500', cat: 'image' },
  { name: 'gamma_folder', isDir: 'true', bytes: '0', cat: 'folder' },
  { name: 'delta[1].js', isDir: 'false', bytes: '300', cat: 'document' },
  { name: 'special(test)*+?.py', isDir: 'false', bytes: '200', cat: 'document' },
  { name: 'backslash\\path.txt', isDir: 'false', bytes: '500', cat: 'document' },
  { name: 'unicode_🚀_中文.pdf', isDir: 'false', bytes: '100', cat: 'document' },
  { name: 'media_sample.mp4', isDir: 'false', bytes: '1200', cat: 'media' },
  { name: 'identical_size_a.txt', isDir: 'false', bytes: '400', cat: 'document' },
  { name: 'identical_size_b.txt', isDir: 'false', bytes: '400', cat: 'document' },
];

testFilesData.forEach(d => {
  const item = new MockElement('div');
  item.classList.add('file-item');
  item.dataset.name = d.name.toLowerCase();
  item.dataset.isDir = d.isDir;
  item.dataset.bytes = d.bytes;
  item.dataset.category = d.cat;
  fileList.appendChild(item);
});

// Re-instantiate or trigger FileExplorerEngine events
// Search Input input event
const searchListeners = searchInput.listeners['input'] || [];

runTest('Search with regex special characters does NOT crash and matches literally', () => {
  assert(searchListeners.length > 0, 'Search input should have input listener');

  const regexSpecialTerms = ['[', '(', '*', '+', '\\', '?', '{', '^', '$', '|'];
  for (const term of regexSpecialTerms) {
    searchInput.value = term;
    assert.doesNotThrow(() => {
      searchListeners[0]({ target: searchInput });
    }, `Search should not throw on term: ${term}`);
  }

  // Verify literal matching for '['
  searchInput.value = '[';
  searchListeners[0]({ target: searchInput });

  const visibleItems = fileList.children.filter(c => c.style.display !== 'none');
  assert.strictEqual(visibleItems.length, 1, 'Only delta[1].js should match [');
  assert.strictEqual(visibleItems[0].dataset.name, 'delta[1].js');
});

runTest('Search with unicode characters matches correctly', () => {
  searchInput.value = '🚀';
  searchListeners[0]({ target: searchInput });
  const visible = fileList.children.filter(c => c.style.display !== 'none');
  assert.strictEqual(visible.length, 1);
  assert.strictEqual(visible[0].dataset.name, 'unicode_🚀_中文.pdf');

  searchInput.value = '中文';
  searchListeners[0]({ target: searchInput });
  const visible2 = fileList.children.filter(c => c.style.display !== 'none');
  assert.strictEqual(visible2.length, 1);
  assert.strictEqual(visible2[0].dataset.name, 'unicode_🚀_中文.pdf');
});

runTest('Search with whitespace: whitespace-only restores all files', () => {
  searchInput.value = '   ';
  searchListeners[0]({ target: searchInput });
  const visible = fileList.children.filter(c => c.style.display !== 'none');
  assert.strictEqual(visible.length, testFilesData.length, 'Whitespace search should show all files');
});

runTest('Clear button ✕ restores full list and focuses search input', () => {
  // First search for something specific
  searchInput.value = 'alpha';
  searchListeners[0]({ target: searchInput });
  assert.strictEqual(fileList.children.filter(c => c.style.display !== 'none').length, 1);

  // Click clear button
  const clearListeners = searchClearBtn.listeners['click'] || [];
  assert(clearListeners.length > 0, 'Clear button should have listener');
  clearListeners[0]();

  assert.strictEqual(searchInput.value, '', 'Search input should be cleared');
  assert.strictEqual(searchClearBtn.classList.contains('d-none'), true, 'Clear button hidden');
  const visible = fileList.children.filter(c => c.style.display !== 'none');
  assert.strictEqual(visible.length, testFilesData.length, 'All files restored after clear');
  assert.strictEqual(searchInput._focused, true, 'Search input focused after clear');
});

runTest('Category filter pill isolates specific category', () => {
  const pillImg = getOrCreateElement('pill-image');
  pillImg.dataset.filter = 'image';
  const pillListeners = pillImg.listeners['click'] || [];
  assert(pillListeners.length > 0, 'Pill should have click listener');
  pillListeners[0]();

  const visible = fileList.children.filter(c => c.style.display !== 'none');
  assert.strictEqual(visible.length, 1);
  assert.strictEqual(visible[0].dataset.name, 'beta.png');

  // Reset category to all
  const pillAll = getOrCreateElement('pill-all');
  pillAll.dataset.filter = 'all';
  (pillAll.listeners['click'] || [])[0]();
  assert.strictEqual(fileList.children.filter(c => c.style.display !== 'none').length, testFilesData.length);
});

runTest('Sorting: Folders are always sorted first regardless of sort direction', () => {
  const sortListeners = sortSelect.listeners['change'] || [];
  assert(sortListeners.length > 0, 'Sort select should have change listener');

  // Name asc
  sortSelect.value = 'name-asc';
  sortListeners[0]({ target: sortSelect });
  assert.strictEqual(fileList.children[0].dataset.isDir, 'true', 'Folder should be first in name-asc');

  // Name desc
  sortSelect.value = 'name-desc';
  sortListeners[0]({ target: sortSelect });
  assert.strictEqual(fileList.children[0].dataset.isDir, 'true', 'Folder should be first in name-desc');

  // Size desc
  sortSelect.value = 'size-desc';
  sortListeners[0]({ target: sortSelect });
  assert.strictEqual(fileList.children[0].dataset.isDir, 'true', 'Folder should be first in size-desc');
});

runTest('Sorting: Identical sizes maintain stable ordering without crashing or NaN', () => {
  sortSelect.value = 'size-desc';
  (sortSelect.listeners['change'] || [])[0]({ target: sortSelect });

  const names = fileList.children.map(c => c.dataset.name);
  const idxA = names.indexOf('identical_size_a.txt');
  const idxB = names.indexOf('identical_size_b.txt');
  assert(idxA !== -1 && idxB !== -1, 'Both identical size items should exist');
  assert.strictEqual(Math.abs(idxA - idxB), 1, 'Items with identical size must be contiguously grouped in sorted list');
});

runTest('Empty state appears when no files match search', () => {
  searchInput.value = 'nonexistent_query_xyz';
  searchListeners[0]({ target: searchInput });

  const visible = fileList.children.filter(c => c.style.display !== 'none');
  assert.strictEqual(visible.length, 0);
  assert.strictEqual(emptySearchState.classList.contains('d-none'), false, 'Empty state visible');
  assert.strictEqual(searchTermDisplay.textContent, 'nonexistent_query_xyz');
});

// ============================================================================
// FOCUS 5: Remediation Verification (Toast textContent XSS Prevention)
// ============================================================================
console.log('\n--- Focus 5: Remediation Verification ---');

runTest('REMEDIATION VERIFICATION: Toast Notification System prevents DOM XSS injection', () => {
  const xssPayload = '<img src=x onerror=alert(1)>';
  mockWindow.showToast('danger', `Failed to delete '${xssPayload}'`);

  const lastToast = toastContainer.children[toastContainer.children.length - 1];
  const renderedHtml = lastToast.innerHTML;

  assert(!renderedHtml.includes(xssPayload), 'XSS payload must NOT be executed or present unescaped in innerHTML');
  console.log('    [+] CONFIRMED REMEDIATION: showToast prevents DOM XSS!');
});

console.log('\n======================================================================');
console.log(`DOM TEST RESULTS: ${passCount} PASSED, ${failCount} FAILED`);
console.log('======================================================================\n');

if (failCount > 0) {
  process.exit(1);
} else {
  process.exit(0);
}
