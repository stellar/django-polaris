(function () {
    let section = document.querySelector(".main-content").firstElementChild;
    let button = document.createElement("button");
    button.className = "button";
    button.innerHTML = "Skip Confirmation";
    button.setAttribute("test-action", "submit");
    button.addEventListener("click", function () {
        this.disabled = true;
        let url =
            window.location.protocol +
            "//" +
            window.location.host +
            "/skip_confirm_email";
        fetch(url)
            .then((res) => res.json())
            .then((json) => {
                if (json["status"] === "not found") {
                    // This would only happen if the PolarisStellarAccount doesn't exist.
                    // It should always exist because the user needs to have an existing
                    // account to access the confirm email page.
                    let errElement = document.createElement("p");
                    errElement.style = "color:red";
                    errElement.innerHTML =
                        "Error: Unable to skip confirmation step";
                    errElement.align = "center";
                    section.appendChild(document.createElement("br"));
                    section.appendChild(errElement);
                } else {
                    window.location.reload(true);
                }
            });
    });
    section.appendChild(document.createElement("br"));
    section.appendChild(button);
})();
