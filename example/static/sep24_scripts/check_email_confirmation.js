window.addEventListener("load", () => {
  window.addEventListener("focus", () => {
    // Hit the /webapp endpoint again to check if the user's
    // email has been confirmed.
    window.location.reload(true);
  });
});
