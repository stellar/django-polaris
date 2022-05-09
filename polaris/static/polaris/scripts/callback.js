"use strict";

function callback({
  txJSON,
  onChangeCallback,
  transactionStatus,
  callback,
}) {
  if (onChangeCallback === 'None')
    onChangeCallback = '';
  let url = new URL(window.location);
  let currentStatus = transactionStatus;
  let isInitialLoad = url.searchParams.get('initialLoad');
  let lastStatusChange = url.searchParams.get('lastStatusChange');
  if (isInitialLoad || (lastStatusChange && lastStatusChange !== currentStatus)) {
    if (onChangeCallback.toLowerCase() === 'postmessage') {
      postMessageCallback({
        onChange: true
      });
    } else if (onChangeCallback && isInitialLoad) {
      urlCallback({
        onChange: true
      });
    }
  } else {
    updateURLForOnChangeStatus();
  }

  if (callback.toLowerCase() === 'postmessage') {
    postMessageCallback({
      onChange: false
    });
  } else if (callback) {
    urlCallback({
      onChange: false
    });
  }

  // Callback function to post the serialized transaction to the wallet.
  function postMessageCallback({
    onChange
  }) {
    let targetWindow;

    if (window.opener != void 0) {
      targetWindow = window.opener;
    } else if (window.parent != void 0) {
      targetWindow = window.parent;
    } else {
      return;
    }

    targetWindow.postMessage(JSON.parse(txJSON), "*");
    if (onChange) {
      updateURLForOnChangeStatus();
    } else {
      updateURLWithCallbackSuccess();
    }
  }

  // Callback function to post the serialized transaction to the callback URL
  function urlCallback({
    onChange
  }) {
    let url = onChange ? onChangeCallback : callback;
    fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(txJSON)
    }).catch((e) => {
      console.error(`POST request to ${url} failed.`, e);
    }).then((response) => {
      if (!response.ok) {
        console.error(`POST request to ${url} failed.`, response);
        return;
      }
      if (onChange) {
        updateURLForOnChangeStatus();
      } else {
        updateURLWithCallbackSuccess();
      }
    });
  }

  function updateURLWithCallbackSuccess() {
    let url = new URL(window.location);
    url.searchParams.set("callback", "success");
    if (isInitialLoad) {
      url.searchParams.delete("initialLoad");
    }
    window.history.replaceState({}, '', url);
  }

  function updateURLForOnChangeStatus() {
    let url = new URL(window.location);
    if (isInitialLoad) {
      url.searchParams.delete("initialLoad");
      window.history.replaceState({}, '', url);
    }
    if (onChangeCallback.toLowerCase() === 'postmessage') {
      url.searchParams.set("lastStatusChange", currentStatus);
      window.history.replaceState({}, '', url);
    }
  }
}