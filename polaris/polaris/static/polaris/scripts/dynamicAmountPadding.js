"use strict";

// Amount symbol padding
const amountSymbol = document.querySelector('.icon-symbol');
let amountInputElem, amountSymbolWidthFloat;
if (amountSymbol) {
  amountInputElem = amountSymbol.nextElementSibling;
  amountSymbolWidthFloat = parseFloat(getComputedStyle(amountSymbol).width.replace(/px/, ''));
  amountInputElem.style.paddingLeft = (amountSymbolWidthFloat + 2).toString() + 'px';
}
