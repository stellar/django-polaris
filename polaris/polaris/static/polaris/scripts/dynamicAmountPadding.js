"use strict";

// Amount symbol padding
const amountInputElem = document.querySelector('.amount-input');
let icon, iconWidthStr, iconWidthFloat;
if (amountInputElem) {
  icon = amountInputElem.previousElementSibling;
  iconWidthStr = getComputedStyle(icon).width;
  iconWidthFloat = parseFloat(iconWidthStr.replace(/px/, ''));
  amountInputElem.style.paddingLeft = (iconWidthFloat + 2).toString() + 'px';
}
