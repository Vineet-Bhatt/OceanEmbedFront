(function () {
  'use strict';
  var link;
  var app;
  var hover;
  var canvas;
  var lastCard = null;
  var leaving = false;

  var TARGET = 'satellite-predict.html';
  var ZOOM_SECONDS = 1.1;

  // Zoom the satellite scene in toward the viewer, fade to the page background,
  // then open the new prediction home page.
  function zoomAndGo(href) {
    if (leaving) return;
    leaving = true;
    link.hidden = true;
    canvas.style.cursor = '';

    var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce || !window.gsap) {
      window.location.href = href;
      return;
    }

    var veil = document.createElement('div');
    veil.id = 'oceanembed-zoom-veil';
    document.body.appendChild(veil);

    document.documentElement.classList.add('oceanembed-zooming');
    window.gsap.to(canvas, {
      scale: 2.4,
      duration: ZOOM_SECONDS,
      ease: 'power3.in',
      transformOrigin: '50% 58%'
    });
    window.gsap.to(veil, {
      opacity: 1,
      duration: ZOOM_SECONDS * 0.55,
      delay: ZOOM_SECONDS * 0.45,
      ease: 'power1.in',
      onComplete: function () { window.location.href = href; }
    });
  }

  // If the browser restores this page from the back/forward cache, undo the zoom.
  window.addEventListener('pageshow', function (event) {
    if (!event.persisted || !leaving) return;
    leaving = false;
    var veil = document.getElementById('oceanembed-zoom-veil');
    if (veil) veil.remove();
    document.documentElement.classList.remove('oceanembed-zooming');
    if (window.gsap && canvas) window.gsap.set(canvas, { clearProps: 'transform' });
  });

  function attach() {
    app = window.__oceanEmbedApp;
    if (!app || !app.graphicsDevice || !app.root) return false;
    canvas = app.graphicsDevice.canvas;
    var group = app.root.findByName('cardsgroup');
    hover = group && group.script && group.script.cardHover;
    if (!hover) return false;

    link = document.createElement('a');
    link.id = 'oceanembed-predict-cta';
    link.href = TARGET;
    link.textContent = 'PREDICT';
    link.setAttribute('aria-label', 'Open the OceanEmbed prediction page');
    link.hidden = true;
    link.addEventListener('click', function (event) {
      // Keep modified clicks (new tab, etc.) working normally.
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.button) return;
      event.preventDefault();
      zoomAndGo(link.href);
    });
    document.body.appendChild(link);

    function updateHover(event) {
      if (leaving) return;
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
      if (leaving) return;
      hover._hasMouse = false;
      if (hover.update) hover.update();
      link.hidden = true;
      canvas.style.cursor = '';
    });
    canvas.addEventListener('pointerdown', function (event) {
      updateHover(event);
      if (lastCard && event.pointerType !== 'mouse') zoomAndGo(link.href);
    });
    canvas.addEventListener('click', function (event) {
      updateHover(event);
      if (lastCard) zoomAndGo(link.href);
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
