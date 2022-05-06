"use strict";

// Disable form submit buttons after first click
let submitButton = document.querySelector('.submit');
let anchorForm = document.querySelector('form');
if (anchorForm) {
  anchorForm.addEventListener('submit', (e) => {
    submitButton.disabled = true;
  });
}
