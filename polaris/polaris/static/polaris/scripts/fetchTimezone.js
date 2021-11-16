"use strict";

function fetchTimezone({tzEndpoint, sessionId, sessionOffset }) {
  if (!(tzEndpoint && sessionId))
    return;
  const currentOffset = new Date().getTimezoneOffset() * -1;
  console.log(currentOffset)
  console.log(sessionOffset)
  if (currentOffset == sessionOffset)
    return;
  fetch(tzEndpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      sessionId: sessionId,
      sessionOffset: currentOffset
    })
  });
}
