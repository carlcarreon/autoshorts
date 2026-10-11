const form = document.querySelector('#generate-form');
const topic = document.querySelector('#topic');
const button = document.querySelector('#generate-button');
const loading = document.querySelector('#loading');
const error = document.querySelector('#error');
const result = document.querySelector('#result');
const video = document.querySelector('#video');
let generating = false;

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (generating) return;
  const question = topic.value.trim();
  if (!question) {
    error.textContent = 'Enter a topic or question.';
    error.hidden = false;
    topic.focus();
    return;
  }
  generating = true;
  button.disabled = true;
  topic.disabled = true;
  form.setAttribute('aria-busy', 'true');
  loading.hidden = false;
  error.hidden = true;
  result.hidden = true;
  video.pause();
  try {
    const response = await fetch('/generate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({topic: question}),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Could not generate your video. Please try again.');
    video.src = data.video_url;
    video.load();
    document.querySelector('#download').href = data.download_url;
    result.hidden = false;
    result.scrollIntoView({behavior: 'smooth', block: 'start'});
  } catch (failure) {
    error.textContent = failure instanceof TypeError || failure instanceof SyntaxError
      ? 'Could not connect to AutoShorts. Check that the local server is running.'
      : failure.message;
    error.hidden = false;
  } finally {
    generating = false;
    button.disabled = false;
    topic.disabled = false;
    form.setAttribute('aria-busy', 'false');
    loading.hidden = true;
  }
});

video.addEventListener('error', () => {
  error.textContent = 'The video could not be loaded. Try the Download MP4 link or generate again.';
  error.hidden = false;
});
