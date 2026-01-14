document.getElementById("check").addEventListener("click", () => {
  const password = document.getElementById("password").value;
  const start = parseInt(document.getElementById("start").value);
  const end = parseInt(document.getElementById("end").value);

  const result = document.getElementById("result");

  if (isNaN(start) || isNaN(end)) {
    result.textContent = "Invalid range";
    result.style.color = "red";
    return;
  }

  // Preserve leading zeros by string comparison
  let found = false;
  for (let i = start; i <= end; i++) {
    if (i.toString() === password) {
      found = true;
      break;
    }
  }

  if (found) {
    result.textContent = "Password is within range ?";
    result.style.color = "green";
  } else {
    result.textContent = "Password NOT in range ?";
    result.style.color = "red";
  }
});