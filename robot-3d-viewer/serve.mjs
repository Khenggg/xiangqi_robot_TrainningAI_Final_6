import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
const port = Number(process.argv[2] || 8080);
const types = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".urdf": "application/xml; charset=utf-8",
  ".stl": "application/sla",
};

http
  .createServer((request, response) => {
    const urlPath = decodeURIComponent(request.url.split("?")[0]);
    const filePath = path.join(
      root,
      urlPath === "/" ? "/index.html" : urlPath,
    );
    if (!filePath.startsWith(root)) {
      response.writeHead(403);
      response.end("Forbidden");
      return;
    }
    fs.readFile(filePath, (error, data) => {
      if (error) {
        response.writeHead(404);
        response.end("Not found");
        return;
      }
      const ext = path.extname(filePath).toLowerCase();
      response.writeHead(200, {
        "Content-Type": types[ext] || "application/octet-stream",
      });
      response.end(data);
    });
  })
  .listen(port, () => {
    console.log(`Serving http://localhost:${port}/`);
  });
