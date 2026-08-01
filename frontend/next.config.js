/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',   // produces static HTML/JS in ./out — no Node server needed
  images: { unoptimized: true },  // required for static export
}
module.exports = nextConfig