import { createServer } from 'https';
import { readFileSync } from 'fs';
import { parse } from 'url';
import next from 'next';

const dev = true;
const app = next({ dev, hostname: '127.0.0.1', port: 3000 });
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
  ).listen(3000, '127.0.0.1', () => {
    console.log('> HTTPS Next.js ready on https://127.0.0.1:3000');
  });
});
