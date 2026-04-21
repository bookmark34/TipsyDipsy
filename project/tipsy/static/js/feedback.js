(function () {
  function qs(selector, root) {
    return (root || document).querySelector(selector);
  }

  function qsa(selector, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(selector));
  }

  function setStarsActive(stars, value) {
    stars.forEach(function (btn) {
      var starValue = parseInt(btn.getAttribute('data-value') || '0', 10);
      if (value && starValue <= value) {
        btn.classList.add('is-active');
      } else {
        btn.classList.remove('is-active');
      }
    });
  }

  var form = qs('#feedbackForm');
  if (!form) return;

  var starsWrap = qs('.td-feedback-stars', form);
  if (!starsWrap) return;

  var inputId = starsWrap.getAttribute('data-rating-input');
  var ratingInput = inputId ? qs('#' + inputId, form) : null;
  var commentInput = qs('textarea[name="comment"]', form);
  var stars = qsa('.td-star', starsWrap);
  var clientError = qs('#td-feedback-client-error', form);

  function showClientError(message) {
    if (!clientError) return;
    clientError.textContent = message;
    clientError.classList.remove('d-none');
  }

  function hideClientError() {
    if (!clientError) return;
    clientError.textContent = '';
    clientError.classList.add('d-none');
  }

  // Restore existing value (useful if server-side validation fails)
  if (ratingInput && ratingInput.value) {
    var existing = parseInt(ratingInput.value, 10);
    if (!isNaN(existing)) {
      setStarsActive(stars, existing);
    }
  }

  // Use event delegation so clicks on the <i> icon are handled correctly
  // and to avoid any edge cases where the wrong button gets bound.
  starsWrap.addEventListener('click', function (e) {
    var target = e.target;
    if (!target) return;

    var btn = target.closest ? target.closest('button.td-star') : null;
    if (!btn || !starsWrap.contains(btn)) return;

    e.preventDefault();
    hideClientError();

    var raw = btn.getAttribute('data-value');
    var value = raw ? parseInt(raw, 10) : NaN;
    if (isNaN(value) || value < 1 || value > 5) return;

    if (ratingInput) {
      ratingInput.value = String(value);
    }
    setStarsActive(stars, value);
  });

  form.addEventListener('submit', function (e) {
    hideClientError();

    var ratingVal = ratingInput && ratingInput.value ? parseInt(ratingInput.value, 10) : null;
    var commentVal = commentInput && commentInput.value ? commentInput.value.trim() : '';

    var hasRating = ratingVal !== null && !isNaN(ratingVal);
    var hasComment = !!commentVal;

    if (!hasRating && !hasComment) {
      e.preventDefault();
      showClientError('Please provide at least a rating or a comment.');
      return;
    }

    if (hasRating && (ratingVal < 1 || ratingVal > 5)) {
      e.preventDefault();
      showClientError('Rating must be between 1 and 5.');
      return;
    }
  });
})();
