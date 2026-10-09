document.querySelector("#login").addEventListener("submit", async event => {
  event.preventDefault();
  const response = await fetch("/studio/login", {method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({role: document.querySelector("#role").value, password: document.querySelector("#password").value})});
  document.querySelector("#password").value = "";
  if (response.ok) location.assign("/studio");
  else document.querySelector("#message").textContent = "Sign in failed. Check credentials or wait if rate limited.";
});