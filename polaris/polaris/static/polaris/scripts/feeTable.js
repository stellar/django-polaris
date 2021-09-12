"use strict";

/*
* CSS style for :invalid input
* color: #e64755;
* box-shadow: 0 0 0.25rem rgba(230, 71, 85, 0.6), 0 0 0.125rem #e64755;
*/

function feeTable({
  operation,
  additiveFeesEnabled,
  depositFeeFixed,
  depositFeePercent,
  withdrawalFeeFixed,
  withdrawalFeePercent,
  significantDecimals,
  symbol,
  useFeeEndpoint,
  assetCode,
  languageCode,
  parseNumber,
  formatNumber
}) {
  let amountInput = document.querySelector('.amount-input');
  let typeInput = document.querySelector('#id_type');
  let feeTag = document.querySelector('.fee');
  let amountOutTag = document.querySelector('.amount-out');
  let feeTable = document.querySelector('.fee-table');
  let op = operation;
  let fee_fixed;
  let fee_percent;
  let timeout; // timeout must persist outside function scope
  if (op === "deposit") {
    fee_fixed = depositFeeFixed;
    fee_percent = depositFeePercent;
  } else {
    fee_fixed = withdrawalFeeFixed;
    fee_percent = withdrawalFeePercent;
  }
  if (amountInput) {
    if (feeTable)
      feeTable.removeAttribute('hidden');
    amountInput.addEventListener("keyup", amountInputChange);
    if (typeInput)
      typeInput.addEventListener("input", amountInputChange);
    if (amountInput.value)
      // calculate value if the value is pre-filled
      amountInputChange();
  }

  function getFeeTableStrings(fee, amountIn) {
    /*
     * Calculates the total based on the amount entered and returns the strings
     * to be rendered in the fee table.
     */
    let feeStr;
    let totalStr;
    if (amountIn !== 0) {
      let total = additiveFeesEnabled ? amountIn + fee : amountIn - fee;
      feeStr = formatNumber(fee, languageCode, { maximumFractionDigits: significantDecimals });
      totalStr = formatNumber(total, languageCode, { maximumFractionDigits: significantDecimals });
    } else {
      feeStr = "0";
      totalStr = additiveFeesEnabled ? formatNumber(amountIn, languageCode, { maximumFractionDigits: significantDecimals }) : "0";
    }
    return [feeStr, totalStr];
  }

  function updateFeeTableHtml(feeStr, amountOutStr) {
    feeTag.innerHTML = symbol + " " + feeStr;
    amountOutTag.innerHTML = symbol + " " + amountOutStr;
  }

  function callFeeEndpoint(amount) {
    /*
     * Calls the anchor's /fee endpoint.
     *
     * Note that this function may return prior to receiving a response from
     * the server and updating the fee table's HTML.
     *
     * If typeInput is present but no value has been selected, this function
     * will return without making the API call and updating the html.
     *
     * Uses timeouts to ensure a call to the /fee endpoint is only made once
     * every 500 milliseconds.
     */
    clearTimeout(timeout)
    timeout = setTimeout(() => {
      let params = new URLSearchParams({
        "operation": op,
        "asset_code": assetCode,
        "amount": amount
      });
      if (typeInput) {
        if (!typeInput.value) return;
        params.append('type', typeInput.value);
      }
      fetch("/sep24/fee?" + params.toString()).then(
        response => response.json()
      ).then(json => {
        if (!json.error) {
          let [feeStr, totalStr] = getFeeTableStrings(json.fee, amount);
          updateFeeTableHtml(feeStr, totalStr);
        }
      });
    }, 500);
  }

  function isAmountValid() {
    const re = new RegExp('^\\d+((\\.|\\,)\\d{1,2})?$');
    return re.test(amountInput.value);
  }

  function styleAmountInFieldInvalid() {
    amountInput.style.color = "#e64755";
    amountInput.style.boxShadow = "0 0 0.25rem rgba(230, 71, 85, 0.8)";
  }

  function styleAmountInFieldValid() {
    amountInput.style.color = "#ffffff";
    amountInput.style.boxShadow = "none";
  }

  function amountInputChange(e) {
    if (!amountInput.value || Number.isNaN(amountInput.value)) return;
    if (isAmountValid()) {
      styleAmountInFieldValid();
      console.log("valid")
    } else {
      styleAmountInFieldInvalid();
      console.log("not valid")
    }
    if (typeInput && !typeInput.value) {
      return;
    }
    let amountIn = parseNumber(amountInput.value, languageCode);
    if (feeTable) {
      if (!useFeeEndpoint) {
        let fee = fee_fixed + (amountIn * (fee_percent / 100));
        let [feeStr, amountOutStr] = getFeeTableStrings(fee, amountIn);
        updateFeeTableHtml(feeStr, amountOutStr);
      } else {
        callFeeEndpoint(amountIn);
      }
    }
  }
}