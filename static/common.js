// 모든 화면이 같이 쓰는 도구. 전역에는 Survey 하나만 둔다.
// - 서버 응답은 JSON.parse 로만 읽는다 (eval 금지).
// - 사용자 글자는 textContent 로만 넣는다. innerHTML 에 문자열을 이어 붙이지 않는다 (XSS 방지).
"use strict";

var Survey = (function () {
  // ?code=abc → "abc". kind 가 "code" 면 소문자·숫자만, "id" 면 숫자만 남긴다.
  function param(name, kind) {
    var value = new URLSearchParams(location.search).get(name) || "";
    return kind === "id" ? value.replace(/[^0-9]/g, "") : value.replace(/[^a-z0-9]/g, "");
  }

  // el("p", {class: "muted", text: "안녕"}, [자식…]) → DOM 요소
  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (key) {
      var value = attrs[key];
      if (value === null || value === undefined || value === false) return;
      if (key === "text") node.textContent = String(value);
      else if (key === "class") node.className = value;
      else if (key.slice(0, 2) === "on") node.addEventListener(key.slice(2), value);
      else if (value === true) node.setAttribute(key, "");
      else node.setAttribute(key, String(value));
    });
    (children || []).forEach(function (child) {
      if (child === null || child === undefined || child === false) return;
      node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
    });
    return node;
  }

  function replace(target, children) {
    var node = typeof target === "string" ? document.getElementById(target) : target;
    node.replaceChildren.apply(node, children.filter(Boolean));
  }

  // 서버 호출. 성공하면 응답 JSON, 실패하면 사람이 읽을 메시지를 담은 Error 를 던진다.
  // options.admin: 관리 쓰기 요청 → 서버가 CSRF 방어로 요구하는 X-Requested-With 헤더를 붙인다.
  async function api(method, url, body, options) {
    var headers = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (options && options.admin) headers["X-Requested-With"] = "XMLHttpRequest";
    var res;
    try {
      res = await fetch(url, {method: method, headers: headers, cache: "no-store",
                              body: body === undefined ? undefined : JSON.stringify(body)});
    } catch (e) {
      throw new Error("서버에 연결할 수 없습니다. 서버가 켜져 있는지 확인하세요.");
    }
    var text = await res.text();
    var data = null;
    try { data = JSON.parse(text); } catch (e) { /* 500 은 JSON 이 아니다 */ }
    if (data && data.result === "OK") return data;
    if (data && data.msg) throw new Error(data.msg);
    if (res.status >= 500) throw new Error("서버 오류가 났습니다 (" + res.status + "). 서버 콘솔을 확인하세요.");
    throw new Error("요청을 처리하지 못했습니다 (" + res.status + ").");
  }

  // 결과·안내 카드 (제목 + 설명 + 링크)
  function notice(title, desc, link) {
    return el("div", {class: "card notice"}, [
      el("h1", {text: title}),
      desc ? el("p", {class: "desc", text: desc}) : null,
      link ? el("p", {}, [el("a", {href: link.href, text: link.text})]) : null,
    ]);
  }

  function errorCard(message) {
    return el("div", {class: "card notice error-card", role: "alert", text: message});
  }

  return {param: param, el: el, replace: replace, api: api, notice: notice, errorCard: errorCard};
})();
