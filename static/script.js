// === Helper: Temporary toast messages ===
function showTempMessage(msg) {
  const toast = document.createElement('div');
  toast.textContent = msg;
  toast.style.position = 'fixed';
  toast.style.bottom = '20px';
  toast.style.left = '50%';
  toast.style.transform = 'translateX(-50%)';
  toast.style.background = '#333';
  toast.style.color = '#fff';
  toast.style.padding = '10px 20px';
  toast.style.borderRadius = '5px';
  toast.style.zIndex = '9999';
  document.body.appendChild(toast);
  setTimeout(() => { toast.remove(); }, 1000);
}

// === Search ===
document.addEventListener('DOMContentLoaded', () => {
  // Make sure the input id matches your HTML, e.g. 'search' or 'searchInput'
  const searchInput = document.getElementById('searchInput') || document.getElementById('search');
  const threadList = document.getElementById('thread-list-inner');

  if (!searchInput || !threadList) return; // Prevent errors if elements are missing

  function debounce(func, delay) {
    let timeout;
    return (...args) => {
      clearTimeout(timeout);
      timeout = setTimeout(() => func.apply(this, args), delay);
    };
  }

  function filterThreads(query = '') {
    const threads = Array.from(threadList.getElementsByClassName('thread'));
    const lowerQuery = query.toLowerCase();

    threads.forEach(thread => {
      const phone = thread.querySelector('.thread-phone')?.textContent.toLowerCase() || '';
      const body = thread.querySelector('.thread-body')?.textContent.toLowerCase() || '';
      thread.style.display = (phone.includes(lowerQuery) || body.includes(lowerQuery)) ? '' : 'none';
    });
  }

  const debouncedSearch = debounce(() => {
    const query = searchInput.value.trim();
    filterThreads(query);
  }, 200);

  searchInput.addEventListener('input', debouncedSearch);
});

// ===== Filters for Inbox / Sent / All =====
function setBoxFilter(box) {
    const url = new URL(window.location.href);
    url.searchParams.set('box', box);
    url.searchParams.set('page', 1); // reset page to 1
    window.location.href = url.toString();
}

document.addEventListener('DOMContentLoaded', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const box = urlParams.get('box') || 'inbox';
    ["inboxBtn", "unreadBtn", "sentBtn", "allBtn"].forEach(id =>
        document.getElementById(id).classList.remove("active")
    );
    const filterDropdown = document.querySelector(".tag-filter-dropdown");
      if (filterDropdown) {
        const toggle = filterDropdown.querySelector(".tag-filter-toggle");
        const menu = filterDropdown.querySelector(".tag-filter-menu");
        const options = menu.querySelectorAll(".tag-option");
        const applyBtn = menu.querySelector(".apply-tags");

        // === Hover to open/close ===
        filterDropdown.addEventListener("mouseenter", () => {
          filterDropdown.classList.add("open");
        });
        filterDropdown.addEventListener("mouseleave", () => {
          filterDropdown.classList.remove("open");
        });

        // Preselect from URL
        const urlParams = new URLSearchParams(window.location.search);
        let selectedTags = urlParams.getAll("tags");

        // Default Inbox filter exclusions
        if (!selectedTags.length) {
          const box = urlParams.get("box") || "inbox";
          if (box === "inbox") {
            const exclude = ["DNC", "Wrong Number", "Not interested", "__ALL__", "Unverified"];
            selectedTags = Array.from(options)
              .map(o => o.dataset.value)
              .filter(v => !exclude.includes(v));
          }
        }

        // Highlight selected tags
        options.forEach(opt => {
          if (selectedTags.includes(opt.dataset.value)) {
            opt.classList.add("selected");
          }
        });

        // === Track changes ===
        function updateApplyState() {
          const current = Array.from(menu.querySelectorAll(".tag-option.selected"))
            .map(o => o.dataset.value)
            .sort();
          const baseline = [...selectedTags].sort();

          const changed = JSON.stringify(current) !== JSON.stringify(baseline);
          applyBtn.classList.toggle("disabled", !changed);
        }
        updateApplyState(); // initial check

        // Toggle highlight on click
        options.forEach(opt => {
          opt.addEventListener("click", (e) => {
            e.stopPropagation();
            opt.classList.toggle("selected");
            updateApplyState();
          });
        });

        // Apply button → refresh page if active
        applyBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          if (applyBtn.classList.contains("disabled")) return;

          const selected = Array.from(menu.querySelectorAll(".tag-option.selected"))
            .map(o => o.dataset.value);

          const url = new URL(window.location.href);
          url.searchParams.delete("tags");
          selected.forEach(tag => url.searchParams.append("tags", tag));
          url.searchParams.set("page", 1);

          window.location.href = url.toString();
        });
      }

});


function updateFilterButtons(activeBox) {
  ['inboxBtn','unreadBtn','sentBtn','allBtn'].forEach(id => {
    const btn = document.getElementById(id);
    if (btn) btn.classList.toggle('active', id === activeBox+'Btn');
  });
}

// === Toggle Select All / Export Selected ===
function toggleSelectAll() {
  const checkboxes = document.querySelectorAll('.thread-checkbox');
  const anyUnchecked = Array.from(checkboxes).some(cb => !cb.checked);
  checkboxes.forEach(cb => cb.checked = anyUnchecked);
}

function getSelectedPhones() {
  return Array.from(document.querySelectorAll('.thread-checkbox:checked')).map(cb => cb.getAttribute('data-phone'));
}

function exportSelectedThreads() {
  const selectedPhones = getSelectedPhones();
  if (!selectedPhones.length) return showTempMessage('No threads selected for export.');

  fetch('/export-contacts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phones: selectedPhones })
  })
    .then(r => r.blob())
    .then(blob => {
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'selected_contacts.csv';
      document.body.appendChild(a);
      a.click();
      a.remove();
      showTempMessage('Export successful!');
    })
    .catch(err => showTempMessage('Export failed: ' + err.message));
}

// === Add / Call functions ===
function addToLeadsPhone(phone) {
  fetch("/add-to-leads", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone: phone })
  })
  .then(res => res.json())
  .then(data => {
    if (data.success) alert("✅ Added " + phone + " to Leads");
    else alert("❌ Failed to add: " + (data.error || "unknown error"));
  });
}

function callContact(phone) {
  fetch("/call", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone: phone })
  })
  .then(res => res.json())
  .then(data => {
    if (data.success) alert("📞 Calling " + (data.lead || phone) + "\nCaller ID: " + (data.from_number || ''));
    else alert("❌ Call failed: " + data.error);
  });
}

function addToLeads() {
  if (!currentPhone) return showTempMessage("Please select a thread to add to leads.");
  fetch("/add-to-leads", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone: currentPhone })
  })
  .then(res => res.json())
  .then(data => {
    if (data.success) showTempMessage("Lead added to memory. Will be saved to Leads.csv on app exit.");
    else showTempMessage("Error: " + data.error);
  })
  .catch(err => showTempMessage("An unexpected error occurred: " + err));
}

// === Globals ===
let boxFilter = "all"; 
// Use the same tags as backend (TAGS in Ace_Messenger.py)
const tags = [
  "Hot", "Nurture", "Drip", "Qualified", "Wrong Number", "Not interested", "DNC"
];
const tagIcons = {
  "Hot": "🔥",
  "Nurture": "🌱",
  "Drip": "💧",
  "Qualified": "✅",
  "Wrong Number": "❌",
  "Not interested": "🚫",
  "DNC": "📵",
  "No tag": "🏷️"
};

let selectedtag = "";
let currentPhone = null;

// === Page reload ===
// === Page reload with AJAX ===
function goToPage(pageNumber) {
  const params = new URLSearchParams(window.location.search);
  params.set('page', pageNumber);

  if (boxFilter && boxFilter !== 'all') params.set('box', boxFilter);

  const checkedtags = Array.from(document.querySelectorAll('.tag-filter:checked')).map(cb => cb.value);
  if (checkedtags.length && !checkedtags.includes("__ALL__")) {
    params.set('tags', checkedtags.join(","));
  } else {
    params.delete('tags');
  }

  const searchEl = document.getElementById('search');
  if (searchEl && searchEl.value) params.set('search', searchEl.value);

  fetch('/threads?' + params.toString())
    .then(res => res.text())
    .then(html => {
      const tempDiv = document.createElement('div');
      tempDiv.innerHTML = html;

      const newThreadList = tempDiv.querySelector('#thread-list-inner');
      const threadListInner = document.getElementById('thread-list-inner');
      if (threadListInner && newThreadList) threadListInner.innerHTML = newThreadList.innerHTML;

      attachNoteTooltips();

      let selectedThread = document.querySelector('.thread.selected');
      if (selectedThread) {
        loadThread(selectedThread.getAttribute('id').replace('thread-', ''));
      } else {
        let firstThread = document.querySelector('.thread');
        if (firstThread) loadThread(firstThread.getAttribute('id').replace('thread-', ''));
      }

      updateThreadCount();
    });
}

document.getElementById('tagFilterDropdown').addEventListener('change', (e) => {
  selectedtag = e.target.value;
  goToPage(1);
});

const socket = io();

// Keep track of banners by phone number
const activeBanners = {}; // { phone: { banner, count, timeout } }

socket.on("new_message", data => {
  const { phone, body, direction, timestamp } = data;

  // === 🔔 Popup banner notification with counter ===
  if (activeBanners[phone]) {
    // Banner already exists, increment count and update text
    const info = activeBanners[phone];
    info.count++;
    info.banner.textContent = `📩 ${direction} message from ${phone}: "${body}" (${info.count} new messages)`;

    // Reset auto-remove timer
    clearTimeout(info.timeout);
    info.timeout = setTimeout(() => {
      if (info.banner.parentNode) info.banner.remove();
      delete activeBanners[phone];
    }, 5000);

  } else {
    // Create new banner
    const banner = document.createElement("div");
    banner.className = "notify-banner";
    banner.textContent = `📩 ${direction} message from ${phone}: "${body}" (1 new message)`;

    // Click → open thread immediately and remove banner
    banner.addEventListener("click", () => {
      loadThread(phone);
      if (activeBanners[phone]) {
        clearTimeout(activeBanners[phone].timeout);
        delete activeBanners[phone];
      }
      banner.remove();
    });

    document.body.appendChild(banner);

    // Auto-remove after 5 seconds
    const timeout = setTimeout(() => {
      if (banner.parentNode) banner.remove();
      delete activeBanners[phone];
    }, 5000);

    // Track this banner
    activeBanners[phone] = { banner, count: 1, timeout };
  }

  // === Existing chat logic ===
  appendMessage(phone, body, direction, timestamp);
  updateThreadPreview(phone, body, timestamp);

  if (direction === "inbound" && currentPhone !== phone) {
    markThreadUnread(phone);
  }

  bumpThreadToTop(phone);

  if (currentPhone && currentPhone === phone) {
    loadThread(currentPhone);
  }

  playNotificationSound();
});



socket.on("meta_updated", data => {
  if (currentPhone && currentPhone === data.phone) loadThread(currentPhone);
});

// === Thread reload (unchanged except adds badge support) ===
function reloadThreads() {
  const params = new URLSearchParams(window.location.search);

  if (boxFilter && boxFilter !== 'all') params.set('box', boxFilter);

  const checkedtags = Array.from(document.querySelectorAll('.tag-filter:checked')).map(cb => cb.value);
  if (checkedtags.length && !checkedtags.includes("__ALL__")) {
    params.set('tags', checkedtags.join(","));
  } else {
    params.delete('tags');
  }

  const searchEl = document.getElementById('search');
  if (searchEl && searchEl.value) params.set('search', searchEl.value);

  // --- Date filters ---
  const fromDate = document.getElementById('from-date').value;
  const toDate = document.getElementById('to-date').value;
  if (fromDate) params.set('from', fromDate);
  else params.delete('from');
  if (toDate) params.set('to', toDate);
  else params.delete('to');

  fetch('/threads?' + params.toString())
    .then(res => res.text())
    .then(html => {
      const tempDiv = document.createElement('div');
      tempDiv.innerHTML = html;

      const newThreadList = tempDiv.querySelector('#thread-list-inner');
      const threadListInner = document.getElementById('thread-list-inner');
      if (threadListInner && newThreadList) {
        threadListInner.innerHTML = newThreadList.innerHTML;
      }

      attachNoteTooltips();

      // Keep selection if possible
      if (currentPhone) {
        const threadDiv = document.getElementById('thread-' + currentPhone);
        if (threadDiv) loadThread(currentPhone);
      }

      updateThreadCount();
    });
}

// ============================
// Thread Tag Menu JS
// Works with your Jinja thread template
// ============================

const threadList = document.getElementById('thread-list');

if (threadList) {
  // Event delegation for clicks inside the thread list
  threadList.addEventListener('click', (e) => {

    // 1️⃣ Clicked a tag-option icon
    const option = e.target.closest('.tag-option');
    if (option) {
      const wrapper = option.closest('.thread-tag-wrapper');
      const chip = wrapper.querySelector('.chip');
      const newTag = option.dataset.tag;
      const phone = chip.dataset.phone;

      // If Drip, trigger drip assignment popup
      if (newTag === 'Drip') {
        showDripAssignmentPopup(phone);
        return;
      }

      // Update backend (AJAX)
      fetch('/update-meta', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone: phone, tag: newTag })
      }).then(() => {
        // Optionally reload thread if open
        if (currentPhone === phone) loadThread(phone);
      });
      return;
    }

    // 2️⃣ Clicked the chip (open tag menu or assign drip)
    const chip = e.target.closest('.chip');
    if (chip) {
      const wrapper = chip.closest('.thread-tag-wrapper');
      const menu = wrapper.querySelector('.tag-menu');
      const phone = chip.dataset.phone;
      // If Drip chip, open assignment popup
      if (chip.textContent.trim() === '💧') {
        showDripAssignmentPopup(phone);
        return;
      }
      if (menu) {
        // Hide all other menus
        document.querySelectorAll('.thread-tag-wrapper .tag-menu').forEach(m => {
          if (m !== menu) m.style.display = 'none';
        });
        // Toggle this menu
        menu.style.display = menu.style.display === 'block' ? 'none' : 'block';
      }
    }
  });

  // 3️⃣ Hide menus when clicking outside any wrapper
  document.addEventListener('click', (e) => {
    document.querySelectorAll('.thread-tag-wrapper .tag-menu').forEach(menu => {
      if (!menu.closest('.thread-tag-wrapper').contains(e.target)) {
        menu.style.display = 'none';
      }
    });
  });
}

function clearDateFilters() {
  document.getElementById('from-date').value = "";
  document.getElementById('to-date').value = "";
  reloadThreads();
}

// === Auto-apply date filters ===
document.addEventListener("DOMContentLoaded", () => {
  const fromDate = document.getElementById("from-date");
  const toDate = document.getElementById("to-date");

  if (fromDate) {
    fromDate.addEventListener("change", () => reloadThreads());
  }
  if (toDate) {
    toDate.addEventListener("change", () => reloadThreads());
  }
});

// === Thread count helper ===
function updateThreadCount() {
  const threads = document.querySelectorAll('.thread');
  document.getElementById('threadCount').innerText = threads.length;
}

// === tag chips ===
function rendertagChips(selected) {
  const chipsDiv = document.getElementById('tag-chips');
  chipsDiv.innerHTML = '';
  // Only show one Drip chip, regardless of Drip variants
  let dripName = null;
  if (selected && selected.startsWith('Drip - ')) {
    dripName = selected.slice(7).trim();
  }
  tags.forEach(tag => {
    const chip = document.createElement('span');
    // Highlight assigned drip chip
    chip.className = 'chip tag-chip' + ((selected === tag || (tag === 'Drip' && dripName)) ? ' selected' : '');
    if (tag === 'Drip') {
      chip.textContent = '💧';
      chip.title = dripName ? dripName : 'Drip';
      if (dripName) chip.setAttribute('data-tooltip', dripName);
      chip.onclick = () => {
        selectedtag = 'Drip';
        rendertagChips(selectedtag);
        showDripAssignmentPopup(currentPhone);
      };
    } else {
      chip.textContent = tagIcons[tag] || "🏷️";
      chip.title = tag;
      chip.onclick = () => {
        selectedtag = tag;
        rendertagChips(selectedtag);
        autoSaveMeta();
        updateThreadtagChip(currentPhone, selectedtag);
      };
    }
    chip.style.cursor = 'pointer';
    chipsDiv.appendChild(chip);
  });
}


function updateThreadtagChip(phone, tag) {
  let safePhone = phone.replace(/\+/g, 'plus');
  function getDripName(tag) {
    if (tag && tag.startsWith('Drip - ')) return tag.slice(7).trim();
    return null;
  }
  // Inbox
  let threadDiv = document.getElementById('thread-' + safePhone);
  if (threadDiv) {
    let tagChip = threadDiv.querySelector('span.chip');
    if (tagChip) {
      let dripName = getDripName(tag);
      tagChip.className = 'chip drip-chip' + (tag && tag.startsWith('Drip') ? ' selected' : '');
      tagChip.textContent = dripName ? '💧' : (tagIcons[tag] || tag || "🏷️");
      tagChip.title = dripName ? dripName : tag;
      if (dripName) {
        tagChip.setAttribute('data-tooltip', dripName);
      } else {
        tagChip.removeAttribute('data-tooltip');
      }
    }
  }
  // Search results
  let searchDiv = document.getElementById('search-thread-' + safePhone);
  if (searchDiv) {
    let tagChip = searchDiv.querySelector('span.chip');
    if (tagChip) {
      let dripName = getDripName(tag);
      tagChip.className = 'chip drip-chip';
      tagChip.textContent = dripName ? 'Drip' : (tagIcons[tag] || tag || "🏷️");
      tagChip.title = dripName ? dripName : tag;
      if (dripName) {
        tagChip.setAttribute('data-tooltip', dripName);
      } else {
        tagChip.removeAttribute('data-tooltip');
      }
    }
  }
}



// === Notes / Meta ===
function autoSaveMeta() {
  const noteVal = document.getElementById("notes").value;
  fetch("/update-meta", {
    method: "POST",
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({phone: currentPhone, tag: selectedtag, notes: noteVal})
  }).then(() => {
    updateThreadtagChip(currentPhone, selectedtag);
    updateThreadNoteIcon(currentPhone, noteVal);
    attachNoteTooltips();
  });
}

function updateThreadNoteIcon(phone, notes) {
  let safePhone = phone.replace(/\+/g, 'plus');

  // Inbox
  let threadDiv = document.getElementById('thread-' + safePhone);
  if (threadDiv) {
    let noteIcon = threadDiv.querySelector('.note-icon');
    if (notes) {
      if (!noteIcon) {
        noteIcon = document.createElement('span');
        noteIcon.className = 'note-icon';
        noteIcon.innerHTML = '&#128221;<span class="note-tooltip">' + notes + '</span>';
        threadDiv.querySelector('.thread-name').appendChild(noteIcon);
      } else {
        noteIcon.innerHTML = '&#128221;<span class="note-tooltip">' + notes + '</span>';
      }
    } else if (noteIcon) {
      noteIcon.remove();
    }
  }

  // Search results
  let searchDiv = document.getElementById('search-thread-' + safePhone);
  if (searchDiv) {
    let noteIcon = searchDiv.querySelector('.note-icon');
    if (notes) {
      if (!noteIcon) {
        noteIcon = document.createElement('span');
        noteIcon.className = 'note-icon';
        noteIcon.innerHTML = '&#128221;<span class="note-tooltip">' + notes + '</span>';
        searchDiv.querySelector('.thread-name').appendChild(noteIcon);
      } else {
        noteIcon.innerHTML = '&#128221;<span class="note-tooltip">' + notes + '</span>';
      }
    } else if (noteIcon) {
      noteIcon.remove();
    }
  }
}


function attachNoteTooltips() {
  const icons = document.getElementsByClassName('note-icon');
  for (let i = 0; i < icons.length; i++) {
    const icon = icons[i];
    const tooltip = icon.querySelector('.note-tooltip');
    if (tooltip) {
      icon.onmouseenter = () => { tooltip.style.visibility = 'visible'; };
      icon.onmouseleave = () => { tooltip.style.visibility = 'hidden'; };
    }
  }
}

// === Load a conversation with unread reset ===
function loadThread(phone) {
  currentPhone = phone;

  // Clear unread badge in both inbox + search
  clearThreadUnread(phone);

  // Highlight selected
  document.querySelectorAll('.thread').forEach(el => el.classList.remove('selected'));
  let threadDiv = document.getElementById('thread-' + phone.replace(/\+/g, "plus"));
  if (threadDiv) threadDiv.classList.add('selected');

  // Responsive: show center only
  if (window.innerWidth < 768) {
    document.getElementById("left").classList.remove("active");
    document.getElementById("center").classList.add("active");
  }

  // Fetch conversation
  fetch("/thread/" + encodeURIComponent(phone))
    .then(r => r.json())
    .then(data => {
      const messagesDiv = document.getElementById("messages");
      messagesDiv.innerHTML = data.messages.map(m => {
        const body = m.body || "";
        const timestamp = m.timestamp || "";
        const messageClass = m.is_outbound ? 'message outbound' : 'message inbound';
        return `
          <div class="${messageClass}">
            <div class="message-content">
              <div class="bubble">${body}</div>
              <div class="message-meta"><div class="timestamp">${timestamp}</div></div>
            </div>
          </div>`;
      }).join("");
      setTimeout(() => { messagesDiv.scrollTop = messagesDiv.scrollHeight; }, 50);

      // Contact info, tags, notes
      document.getElementById("contact-name").innerText = data.csv_name || data.db_name || data.name || phone || "";
      selectedtag = data.tag || "";
      rendertagChips(selectedtag);
      document.getElementById("notes").value = data.notes || "";
      updateThreadCount();

      // Extra contact info
      const contactExtra = document.getElementById("contact-extra");
      if (contactExtra) {
        let allHtml = `<div class="contact-extra-grid">`;
        if (data.contact_headers && data.contact_all) {
          for (let i = 0; i < data.contact_headers.length; i++) {
            const key = data.contact_headers[i];
            const val = data.contact_all[key] || "";
            if (val && val.trim()) {
              if (key.toLowerCase().includes("zillow")) {
                allHtml += `
                  <div class="contact-key">${key}</div>
                  <div class="contact-val"><a href="${val}" target="_blank" rel="noopener noreferrer">${val}</a></div>
                `;
              } else {
                allHtml += `
                  <div class="contact-key">${key}</div>
                  <div class="contact-val">${val}</div>
                `;
              }
            }
          }
        }
        allHtml += "</div>";
        contactExtra.innerHTML = allHtml;
      }

      // Re-attach notes listeners AFTER the notes field is re-rendered
      attachNotesListeners();
    });
}
// Scroll messages to bottom
function scrollMessagesToBottom() {
    const messagesContainer = document.getElementById('messages');
    if (messagesContainer) {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
}

// Call this after loading messages or sending a new message
scrollMessagesToBottom();

// Send message
function sendMsg() {
  const msgBody = document.getElementById("msgBody");
  const message = msgBody.value.trim();
  if (!message) return;
  
  fetch("/send", {
    method: "POST",
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({to: currentPhone, body: message})
  })
  .then(r => r.json())
  .then(() => {
    msgBody.value = "";
    scrollMessagesToBottom();
    loadThread(currentPhone);
  });
}

// Auto-resize textarea
const textarea = document.getElementById('msgBody');
if (textarea) {
  textarea.addEventListener('input', e => {
    textarea.style.height = 'auto';
    textarea.style.height = textarea.scrollHeight + 'px';
  });
}

// === Notes auto-save ===
function saveNotes() {
  const notesEl = document.getElementById("notes");
  if (!notesEl) return;

  const noteContent = notesEl.value.trim();

  fetch("/update-meta", {
    method: "POST",
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phone: currentPhone, tag: selectedtag, notes: noteContent })
  })
  .then(res => res.json())
  .then(() => {
    showTempMessage("Notes saved successfully!");
    updateThreadNoteIcon(currentPhone, noteContent);
    attachNoteTooltips();
  })
  .catch(err => {
    showTempMessage("Error saving notes: " + err.message);
  });
}

function attachNotesListeners() { 
  const notesEl = document.getElementById("notes");
  if (!notesEl) return;

  // Save on blur
  notesEl.addEventListener("blur", saveNotes);

  // Save on Enter (without Shift) and prevent newline
  notesEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();  // block new line
      saveNotes();
    }
  });

  // Toggle "has-content" class
  notesEl.addEventListener("input", () => {
    if (notesEl.value.trim()) {
      notesEl.classList.add("has-content");
    } else {
      notesEl.classList.remove("has-content");
    }
  });

  // Trigger initial state once when attached
  notesEl.dispatchEvent(new Event("input"));
}


document.addEventListener('DOMContentLoaded', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const currentBox = urlParams.get('box') || 'inbox';
    ["inboxBtn","sentBtn","allBtn"].forEach(id =>
        document.getElementById(id).classList.remove("active")
    );
    const activeBtn = document.getElementById(currentBox + "Btn");
    if (activeBtn) activeBtn.classList.add("active");
});



// === Clear Search Button ===
document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.getElementById("search");
  const clearBtn = document.getElementById("clear-search");

  if (!searchInput || !clearBtn) return;

  // Show/hide clear button when typing
  searchInput.addEventListener("input", () => {
    clearBtn.style.display = searchInput.value ? "block" : "none";
  });

  // Clear search when X clicked
  clearBtn.addEventListener("click", () => {
    searchInput.value = "";
    clearBtn.style.display = "none";
    reloadThreads(); // reload full inbox
  });
});


function markThreadUnread(phone) {
  const safePhone = phone.replace(/\+/g, "plus");

  // Inbox
  const threadDiv = document.getElementById("thread-" + safePhone);
  if (threadDiv && !threadDiv.querySelector(".unread-badge")) {
    const nameLabel = threadDiv.querySelector(".thread-name-label");
    if (nameLabel) {
      nameLabel.insertAdjacentHTML("afterend",
        `<span class="unread-badge" style="color:red; margin-left:6px;">●</span>`
      );
    }
  }

  // Search results
  const searchDiv = document.getElementById("search-thread-" + safePhone);
  if (searchDiv && !searchDiv.querySelector(".unread-badge")) {
    const nameLabel = searchDiv.querySelector(".thread-name-label");
    if (nameLabel) {
      nameLabel.insertAdjacentHTML("afterend",
        `<span class="unread-badge" style="color:red; margin-left:6px;">●</span>`
      );
    }
  }
}

function bumpThreadToTop(phone) {
  const safePhone = phone.replace(/\+/g, "plus");

  // Inbox
  const inboxList = document.getElementById("thread-list-inner");
  const threadDiv = document.getElementById("thread-" + safePhone);
  if (threadDiv && inboxList) {
    inboxList.prepend(threadDiv);
  }

  // Search results
  const searchList = document.getElementById("search-results");
  const searchDiv = document.getElementById("search-thread-" + safePhone);
  if (searchDiv && searchList) {
    searchList.prepend(searchDiv);
  }
}

function clearThreadUnread(phone) {
  const safePhone = phone.replace(/\+/g, "plus");

  // Inbox
  const threadDiv = document.getElementById("thread-" + safePhone);
  if (threadDiv) {
    const badge = threadDiv.querySelector(".unread-badge");
    if (badge) badge.remove();
  }

  // Search results
  const searchDiv = document.getElementById("search-thread-" + safePhone);
  if (searchDiv) {
    const badge = searchDiv.querySelector(".unread-badge");
    if (badge) badge.remove();
  }
}
function updateThreadPreview(phone, body, timestamp) {
  const safePhone = phone.replace(/\+/g, "plus");

  // === Inbox thread ===
  const threadDiv = document.getElementById("thread-" + safePhone);
  if (threadDiv) {
    const preview = threadDiv.querySelector(".thread-preview");
    if (preview) preview.textContent = body;

    const timeEl = threadDiv.querySelector(".thread-time");
    if (timeEl) timeEl.textContent = timestamp;
  }

  // === Search results thread ===
  const searchDiv = document.getElementById("search-thread-" + safePhone);
  if (searchDiv) {
    const preview = searchDiv.querySelector(".thread-preview");
    if (preview) preview.textContent = body;

    const timeEl = searchDiv.querySelector(".thread-time");
    if (timeEl) timeEl.textContent = timestamp;
  }
}
function attachTagTooltips() {
  document.querySelectorAll('.thread .chip').forEach(chip => {
    let dripName = chip.getAttribute('data-tooltip');
    if (dripName) {
      chip.addEventListener('mouseenter', function handler() {
        let tip = document.createElement('div');
        tip.className = 'tag-tooltip';
        tip.textContent = dripName;
        chip.appendChild(tip);
      });
      chip.addEventListener('mouseleave', function handler() {
        let tip = chip.querySelector('.tag-tooltip');
        if (tip) tip.remove();
      });
    }
  });
}

document.addEventListener("DOMContentLoaded", attachTagTooltips);
// script.js
// === Drip Assignment Popup Trigger ===
// This function should be called when a tag is set to 'Drip'
function showDripAssignmentPopup(phone) {
  window.currentDripPhone = phone;
  fetch('/drip-automations?popup=1')
    .then(res => res.text())
    .then(html => {
      const popup = document.getElementById('dripPopup');
      popup.innerHTML = html;
      popup.style.display = 'block';
      // Select drip
      popup.querySelectorAll('.select-drip-btn').forEach(btn => {
        btn.addEventListener('click', function() {
          const dripId = btn.getAttribute('data-drip-id');
          assignDripToContact(phone, dripId);
          popup.style.display = 'none';
        });
      });
      // View messages: load popup partial
      popup.querySelectorAll('.view-messages-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
          e.stopPropagation();
          const dripId = btn.getAttribute('data-drip-id');
          fetch(`/drip-messages/${dripId}`)
            .then(res => res.text())
            .then(html => {
              popup.innerHTML = html;
              popup.style.display = 'block';
              attachDripPopupHandlers();
            });
        });
      });
      attachDripPopupHandlers();
    });
}

function assignDripToContact(phone, dripId) {
  fetch('/assign-drip', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phone: phone, drip_id: dripId })
  })
  .then(res => res.json())
  .then(data => {
    if (data.success) {
      showTempMessage('Drip assigned!');
      document.getElementById('dripPopup').style.display = 'none';
      // Immediately update tag chip in thread list and center panel
      updateThreadtagChip(phone, data.new_tag || 'Drip');
      selectedtag = data.new_tag || 'Drip';
      rendertagChips(selectedtag);
    } else {
      showTempMessage('Failed to assign drip: ' + (data.error || 'unknown error'));
    }
  });
}

function attachDripPopupHandlers() {
  const popup = document.getElementById('dripPopup');
  if (!popup) return;
  // Select button
  popup.querySelectorAll('.select-drip-btn').forEach(btn => {
    btn.onclick = function() {
      const dripId = btn.getAttribute('data-drip-id');
      // Always use window.currentDripPhone for context
      if (window.currentDripPhone) {
        assignDripToContact(window.currentDripPhone, dripId);
      } else {
        showTempMessage('Failed to assign drip: Missing phone or drip_id');
      }
    };
  });
  // Back/Cancel button
  popup.querySelectorAll('.close-drip-popup').forEach(btn => {
    btn.onclick = function(e) {
      e.preventDefault();
      popup.style.display = 'none';
    };
  });
  // X button
  const xBtn = popup.querySelector('.drip-popup-close-x');
  if (xBtn) xBtn.onclick = function(e) { e.preventDefault(); popup.style.display = 'none'; };
  // Overlay click
  const overlay = popup.querySelector('.drip-popup-overlay');
  if (overlay) overlay.onclick = (e) => { if (e.target === overlay) popup.style.display = 'none'; };
}

// === Tag change logic: trigger popup if tag is set to 'Drip' ===
function onTagChanged(phone, newTag) {
  if (newTag === 'Drip') {
    showDripAssignmentPopup(phone);
  }
  // ...existing logic for updating tag...
}

