/** @type {import('next').NextConfig} */
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8000';

const nextConfig = {
  reactStrictMode: true,
  // Proxy the API and static garment files through the Next dev server so the
  // browser sees one origin (no CORS, no mixed-origin canvas taint).
  async rewrites() {
    return [
      { source: '/api/:path*', destination: `${API_URL}/api/:path*` },
      { source: '/assets/clothes/:path*', destination: `${API_URL}/assets/clothes/:path*` },
      { source: '/outputs/:path*', destination: `${API_URL}/outputs/:path*` },
    ];
  },
};

export default nextConfig;
