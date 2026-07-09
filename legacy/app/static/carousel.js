document.addEventListener("DOMContentLoaded", () => {
  const bodyPath = document.body.dataset.path || "";
  const carousels = document.querySelectorAll("[data-carousel]");
  const lightbox = document.querySelector("[data-lightbox]");
  const lightboxImage = lightbox?.querySelector("[data-lightbox-image]");
  const lightboxCaption = lightbox?.querySelector("[data-lightbox-caption]");
  const lightboxClose = lightbox?.querySelector("[data-lightbox-close]");
  const lightboxPrev = lightbox?.querySelector("[data-lightbox-prev]");
  const lightboxNext = lightbox?.querySelector("[data-lightbox-next]");
  const toastList = document.querySelector("[data-toast-list]");
  const copyOrderTemplateButton = document.querySelector("[data-copy-order-template]");
  const orderTemplate = document.querySelector("[data-order-template]");
  const adminScrollKey = "admin-scroll-y";

  let activeLightboxItems = [];
  let activeLightboxIndex = 0;

  const updateLightbox = () => {
    const trigger = activeLightboxItems[activeLightboxIndex];
    if (!trigger || !lightboxImage || !lightboxCaption) {
      return;
    }
    lightboxImage.src = trigger.dataset.lightboxSrc || "";
    lightboxImage.alt = trigger.dataset.lightboxAlt || "";
    lightboxCaption.textContent = trigger.dataset.lightboxCaption || "";
    const hasMultipleItems = activeLightboxItems.length > 1;
    lightboxPrev?.toggleAttribute("hidden", !hasMultipleItems);
    lightboxNext?.toggleAttribute("hidden", !hasMultipleItems);
  };

  const closeLightbox = () => {
    lightbox?.close();
    activeLightboxItems = [];
    activeLightboxIndex = 0;
  };

  for (const carousel of carousels) {
    const track = carousel.querySelector("[data-carousel-track]");
    const slides = Array.from(carousel.querySelectorAll("[data-carousel-slide]"));
    const dots = Array.from(carousel.querySelectorAll("[data-carousel-dot]"));
    const prevButton = carousel.querySelector("[data-carousel-prev]");
    const nextButton = carousel.querySelector("[data-carousel-next]");
    const autoplayDelay = Number(carousel.dataset.carouselAutoplay || 0);

    if (slides.length <= 1) {
      continue;
    }

    let currentIndex = 0;
    let autoplayTimer = null;

    const syncSlideMedia = () => {
      slides.forEach((slide, index) => {
        const videos = slide.querySelectorAll("[data-carousel-video]");
        videos.forEach((video) => {
          if (index === currentIndex) {
            video.muted = true;
            const playPromise = video.play();
            if (playPromise && typeof playPromise.catch === "function") {
              playPromise.catch(() => {});
            }
          } else {
            video.pause();
            video.currentTime = 0;
          }
        });
      });
    };

    const render = () => {
      if (track) {
        track.style.transform = `translateX(-${currentIndex * 100}%)`;
      }
      slides.forEach((slide, index) => {
        slide.classList.toggle("is-active", index === currentIndex);
        slide.setAttribute("aria-hidden", index === currentIndex ? "false" : "true");
      });
      dots.forEach((dot, index) => {
        dot.classList.toggle("is-active", index === currentIndex);
      });
      syncSlideMedia();
    };

    prevButton?.addEventListener("click", () => {
      currentIndex = (currentIndex - 1 + slides.length) % slides.length;
      render();
    });

    nextButton?.addEventListener("click", () => {
      currentIndex = (currentIndex + 1) % slides.length;
      render();
    });

    dots.forEach((dot, index) => {
      dot.addEventListener("click", () => {
        currentIndex = index;
        render();
      });
    });

    const stopAutoplay = () => {
      if (autoplayTimer) {
        window.clearInterval(autoplayTimer);
        autoplayTimer = null;
      }
    };

    const startAutoplay = () => {
      if (autoplayDelay < 1) {
        return;
      }
      stopAutoplay();
      autoplayTimer = window.setInterval(() => {
        currentIndex = (currentIndex + 1) % slides.length;
        render();
      }, autoplayDelay);
    };

    if (autoplayDelay > 0) {
      carousel.addEventListener("mouseenter", stopAutoplay);
      carousel.addEventListener("mouseleave", startAutoplay);
      carousel.addEventListener("focusin", stopAutoplay);
      carousel.addEventListener("focusout", startAutoplay);
      document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
          stopAutoplay();
        } else {
          startAutoplay();
        }
      });
    }

    render();
    startAutoplay();
  }

  const lightboxTriggers = document.querySelectorAll("[data-lightbox-trigger]");
  for (const trigger of lightboxTriggers) {
    trigger.addEventListener("click", () => {
      if (!lightbox || !lightboxImage || !lightboxCaption) {
        return;
      }
      const container = trigger.closest("[data-carousel]") || trigger.parentElement;
      activeLightboxItems = Array.from(
        container?.querySelectorAll("[data-lightbox-trigger]") || [trigger],
      );
      activeLightboxIndex = Math.max(activeLightboxItems.indexOf(trigger), 0);
      updateLightbox();
      if (typeof lightbox.showModal === "function") {
        lightbox.showModal();
      }
    });
  }

  lightboxClose?.addEventListener("click", () => {
    closeLightbox();
  });

  const showPreviousLightboxImage = () => {
    if (!activeLightboxItems.length) {
      return;
    }
    activeLightboxIndex =
      (activeLightboxIndex - 1 + activeLightboxItems.length) %
      activeLightboxItems.length;
    updateLightbox();
  };

  const showNextLightboxImage = () => {
    if (!activeLightboxItems.length) {
      return;
    }
    activeLightboxIndex = (activeLightboxIndex + 1) % activeLightboxItems.length;
    updateLightbox();
  };

  lightboxPrev?.addEventListener("click", (event) => {
    event.stopPropagation();
    showPreviousLightboxImage();
  });

  lightboxNext?.addEventListener("click", (event) => {
    event.stopPropagation();
    showNextLightboxImage();
  });

  lightbox?.addEventListener("click", (event) => {
    const clickedImage = event.target.closest("[data-lightbox-image]");
    const clickedControl = event.target.closest(
      "[data-lightbox-close], [data-lightbox-prev], [data-lightbox-next]",
    );
    if (!clickedImage && !clickedControl) {
      closeLightbox();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (!lightbox?.open) {
      return;
    }

    if (event.key === "Escape") {
      event.preventDefault();
      closeLightbox();
      return;
    }

    if (!activeLightboxItems.length) {
      return;
    }

    if (event.key === "ArrowRight") {
      event.preventDefault();
      showNextLightboxImage();
    }

    if (event.key === "ArrowLeft") {
      event.preventDefault();
      showPreviousLightboxImage();
    }
  });

  if (toastList) {
    const toasts = toastList.querySelectorAll("[data-toast]");
    toasts.forEach((toast, index) => {
      window.setTimeout(() => {
        toast.classList.add("is-hiding");
        window.setTimeout(() => {
          toast.remove();
          if (!toastList.querySelector("[data-toast]")) {
            toastList.remove();
          }
        }, 220);
      }, 2800 + index * 180);
    });
  }

  copyOrderTemplateButton?.addEventListener("click", async () => {
    if (!orderTemplate) {
      return;
    }
    const originalText = copyOrderTemplateButton.textContent;
    try {
      await window.navigator.clipboard.writeText(orderTemplate.value);
      copyOrderTemplateButton.textContent = "Copied";
      window.setTimeout(() => {
        copyOrderTemplateButton.textContent = originalText;
      }, 1800);
    } catch (_error) {
      orderTemplate.focus();
      orderTemplate.select();
      copyOrderTemplateButton.textContent = "Select and copy";
      window.setTimeout(() => {
        copyOrderTemplateButton.textContent = originalText;
      }, 2200);
    }
  });

  if (bodyPath === "/admin") {
    const savedScrollY = window.sessionStorage.getItem(adminScrollKey);
    if (savedScrollY) {
      window.scrollTo(0, Number(savedScrollY));
      window.sessionStorage.removeItem(adminScrollKey);
    }

    const adminForms = document.querySelectorAll("main form");
    adminForms.forEach((form) => {
      form.addEventListener("submit", () => {
        window.sessionStorage.setItem(adminScrollKey, String(window.scrollY));
      });
    });
  }
});
