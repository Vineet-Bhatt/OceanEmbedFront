(function () {
  'use strict';
  var link;
  var app;
  var hover;
  var canvas;
  var lastCard = null;

  function attach() {
    app = window.__oceanEmbedApp;
    if (!app || !app.graphicsDevice || !app.root) return false;
    canvas = app.graphicsDevice.canvas;
    var group = app.root.findByName('cardsgroup');
    hover = group && group.script && group.script.cardHover;
    if (!hover) return false;

    link = document.createElement('a');
    link.id = 'oceanembed-predict-cta';
    link.href = 'prediction.html';
    link.textContent = 'PREDICT';
    link.setAttribute('aria-label', 'Open the OceanEmbed prediction page');
    link.hidden = true;
    document.body.appendChild(link);

    function updateHover(event) {
      if (event && hover._onMove) hover._onMove(event);
      if (hover.update) hover.update();
      var selected = hover._current && hover._current.entity && hover._current.entity.name === 'card4';
      link.hidden = !selected;
      if (selected) {
        canvas.style.cursor = 'pointer';
        var rect = canvas.getBoundingClientRect();
        link.style.left = Math.round(rect.left + rect.width / 2) + 'px';
        link.style.top = Math.round(rect.top + rect.height * 0.82) + 'px';
      } else {
        canvas.style.cursor = '';
      }
      lastCard = selected;
    }

    canvas.addEventListener('pointermove', updateHover, { passive: true });
    canvas.addEventListener('pointerleave', function () {
      hover._hasMouse = false;
      if (hover.update) hover.update();
      link.hidden = true;
      canvas.style.cursor = '';
    });
    canvas.addEventListener('pointerdown', function (event) {
      updateHover(event);
      if (lastCard && event.pointerType !== 'mouse') window.location.href = link.href;
    });
    canvas.addEventListener('click', function (event) {
      updateHover(event);
      if (lastCard) window.location.href = link.href;
    });
    window.addEventListener('resize', function () { updateHover(); });
    app.on('update', function () { updateHover(); });
    return true;
  }

  var attempts = 0;
  var timer = window.setInterval(function () {
    if (attach() || ++attempts > 120) window.clearInterval(timer);
  }, 250);
}());
