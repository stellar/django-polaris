"use strict";

// Amount symbol padding
const amountSymbol = document.querySelector('.icon-symbol');
let style, width, paddingRight, amountInputElem;
if (amountSymbol) {
  style = getComputedStyle(amountSymbol);
  width = parseFloat(style.width.replace(/px/, ''));
  paddingRight = parseFloat(style.paddingRight.replace(/px/, ''));
  amountInputElem = amountSymbol.nextElementSibling;
  amountInputElem.style.paddingLeft = (width + paddingRight).toString() + 'px';
}
