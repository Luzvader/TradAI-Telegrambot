import { createServer } from 'https';
import { readFileSync } from 'fs';
import { parse } from 'url';
import next from 'next';

const dev = process.env.NODE_ENV !== 'production';
const hostname = process.env.HOST || '127.0.0.1';
const port = parseInt(process.env.PORT, 10) || 3000;
const app = next({ dev, hostname, port });
const handle = app.getRequestHandler();

const certFile = process.env.SSL_CRT_FILE;
const keyFile = process.env.SSL_KEY_FILE;

if (!certFile || !keyFile) {
  console.error('SSL_CRT_FILE and SSL_KEY_FILE environment variables must be set');
  process.exit(1);
}

app.prepare().then(() => {
  createServer(
    {
      key: readFileSync(keyFile),
      cert: readFileSync(certFile),
    },
    (req, res) => {
      const parsedUrl = parse(req.url, true);
      handle(req, res, parsedUrl);
    }
  ).listen(port, hostname, () => {
    console.log(`> HTTPS Next.js ready on https://${hostname}:${port} (${dev ? 'dev' : 'prod'})`);
  });
});
