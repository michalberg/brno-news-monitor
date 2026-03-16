// Zelený radar - Client-side JS

document.addEventListener('DOMContentLoaded', () => {
  // Smooth scroll to sections via hash links
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
      const target = document.querySelector(this.getAttribute('href'));
      if (target) {
        e.preventDefault();
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  });

  // Add "back to top" button when scrolled
  const backToTop = document.createElement('button');
  backToTop.textContent = '↑';
  backToTop.title = 'Zpět nahoru';
  backToTop.style.cssText = `
    position: fixed; bottom: 1.5rem; right: 1.5rem;
    background: #1a1a2e; color: white;
    border: none; border-radius: 50%;
    width: 40px; height: 40px;
    font-size: 1.1rem; cursor: pointer;
    box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    opacity: 0; transition: opacity 0.3s;
    z-index: 200;
  `;
  document.body.appendChild(backToTop);

  window.addEventListener('scroll', () => {
    backToTop.style.opacity = window.scrollY > 400 ? '1' : '0';
  });

  backToTop.addEventListener('click', () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });

  // Mark external links
  document.querySelectorAll('a[target="_blank"]').forEach(link => {
    if (!link.querySelector('.ext-icon')) {
      link.setAttribute('rel', 'noopener noreferrer');
    }
  });

  // Category filter shortcuts (keyboard)
  document.addEventListener('keydown', e => {
    if (e.altKey) {
      const sections = {
        '1': 'komunalni-politika',
        '2': 'doprava',
        '3': 'kultura',
        '4': 'sport',
        'p': 'sledovane-osoby',
      };
      if (sections[e.key]) {
        const el = document.getElementById(sections[e.key]);
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }
  });
});
