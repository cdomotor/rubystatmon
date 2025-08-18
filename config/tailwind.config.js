// File: tailwind.config.js
// Path: /tailwind.config.js
module.exports = {
  darkMode: 'class', // use the 'dark' class on <html>
  content: [
    './app/views/**/*.erb',
    './app/helpers/**/*.rb',
    './app/javascript/**/*.js',
  ],
  theme: { extend: {} },
  plugins: [],
}
