"use strict";

// Amount symbol padding
const amountSymbol = document.querySelector('.icon-symbol');
if (amountSymbol) {
  const style = getComputedStyle(amountSymbol);
  const width = parseFloat(style.width.replace(/px/, ''));
  const paddingRight = parseFloat(style.paddingRight.replace(/px/, ''));
  const amountInputElem = amountSymbol.nextElementSibling;
  amountInputElem.style.paddingLeft = (width + paddingRight).toString() + 'px';
}
