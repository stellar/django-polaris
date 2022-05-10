"use strict";

function styleHelpers({
  languageCode
}) {

  function _instanceof(left, right) {
    if (right != null && typeof Symbolch !== "undefined" && right[Symbol.hasInstance]) {
      return !!right[Symbol.hasInstance](left);
    } else {
      return left instanceof right;
    }
  }

  // Manually babel-ized helper. Generic helper to wait until conditions are right.
  var waitFor = function waitFor(predicate) {
    var pollInterval = arguments.length > 1 && arguments[1] !== undefined ? arguments[1] : 500;
    return new Promise(function(resolve) {
      var check = function check() {
        var result = predicate();
        if (_instanceof(result, Promise)) {
          result.then(function(isFinished) {
            if (isFinished) {
              resolve();
              return;
            }
            setTimeout(check, pollInterval);
          });
        } else {
          if (result) {
            resolve();
            return;
          }
          setTimeout(check, pollInterval);
        }
      };
      check();
    });
  };

  // Date/time pickers
  if (
    document.querySelector('input.date') !== null ||
    document.querySelector('input.date-time') !== null ||
    document.querySelector('input.time') !== null
  ) {
    var datepickerScript = document.createElement('script');
    datepickerScript.src = "https://unpkg.com/flatpickr@4.6.3/dist/flatpickr.min.js";
    datepickerScript.integrity = "sha512-/0FOmq5fA1cCPM7zk0sx/43nQD5dhBFtS3SqDE2ZAMsxVG2mg3lKNObZL7t5IUP3m1mGJSwkrhFNdjJwKKOo5Q==";
    datepickerScript.crossOrigin = "anonymous";
    datepickerScript.async = true;
    document.body.append(datepickerScript)

    var datepickerScript = document.createElement('script');
    datepickerScript.src = "https://unpkg.com/flatpickr@4.6.3/dist/l10n/index.js"
    datepickerScript.integrity = "sha512-vTbjTzhS5w7Za0eGC5792DwB1dMy3RhB1iimHK6bLzON2E9GP5cqLNPhTauI9hMUf+zhPyyFB5gOLyBWcuBxJg==";
    datepickerScript.crossOrigin = "anonymous";
    datepickerScript.async = true;
    document.body.append(datepickerScript)

    var datepickerScript = document.createElement('link');
    datepickerScript.href = "https://unpkg.com/flatpickr@4.6.3/dist/flatpickr.min.css";
    datepickerScript.integrity = "sha512-mYrP18xfFU3QxE2Mx9Rlm2D8WO4gVJa3v2tlCYW9lELMIsu77EPCOfD4Uumj7AJTeSnoherQQgCi6j11n0Vigg==";
    datepickerScript.crossOrigin = "anonymous";
    datepickerScript.rel = "stylesheet";
    document.head.append(datepickerScript)

    waitFor(function() {
      return !!window.flatpickr
    }).then(function() {
      window.flatpickr.localize(window.flatpickr.l10ns[languageCode]);
      window.flatpickr('input.date');
      window.flatpickr('input.date-time', {
        enableTime: true
      });
      window.flatpickr('input.time', {
        noCalendar: true,
        enableTime: true
      });
    })
  }

  // File picker
  document.querySelectorAll('.file-upload-field').forEach(function(f) {
    f.addEventListener('change', function(e) {
      var filename = e.target.value.replace(/.*(\/|\\)/, '') || 'Select a file';
      e.target.parentElement.setAttribute('data-text', filename);
    })
  })

  // Card inputs
  if (document.querySelector('.cc-number') !== null) {
    // https: //github.com/nosir/cleave.js
    var cleaveScript = document.createElement('script');
    cleaveScript.src = "https://unpkg.com/cleave.js@1.5.3/dist/cleave.min.js";
    cleaveScript.integrity = "sha512-PFVTH0oUSWMIcRnMyDfB0J4f6/BDdO9ZQmekhpT1k+XX3IKe2oKW92bMbB2tH0R0SmvHopeVBUuKkSL/HE04Cg==";
    cleaveScript.crossOrigin = "anonymous";
    cleaveScript.async = true;
    document.body.append(cleaveScript)

    waitFor(function() {
      return window.Cleave
    }).then(function() {
      new Cleave('.cc-number', {
        creditCard: true
      })
      new Cleave('.cc-expiration', {
        date: true,
        datePattern: ['m', 'y']
      })
      new Cleave('.cc-cvv', {
        numeral: true,
        numeralThousandsGroupStyle: 'none',
        numericOnly: true,
      })
    })
  }

}