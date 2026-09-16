import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(root, "..");
const sharedFilesWhitelist = {
  "/shared/physical_geometry.json": path.resolve(repoRoot, "shared", "physical_geometry.json"),
  "/shared/robot_profiles/fr3.json": path.resolve(repoRoot, "shared", "robot_profiles", "fr3.json"),
  "/shared/virtual_fr3_scene.json": path.resolve(repoRoot, "shared", "virtual_fr3_scene.json"),
  "/shared/virtual_physics.json": path.resolve(repoRoot, "shared", "virtual_physics.json"),
  "/shared/virtual_gripper_profile.json": path.resolve(repoRoot, "shared", "virtual_gripper_profile.json"),
  "/shared/xiangqi_start_layout.json": path.resolve(repoRoot, "shared", "xiangqi_start_layout.json"),
};

const port = Number(process.argv[2] || 8080);
const types = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".urdf": "application/xml; charset=utf-8",
  ".stl": "application/sla",
  ".stp": "model/step",
};

http
  .createServer((request, response) => {
    const urlPath = decodeURIComponent(request.url.split("?")[0]);
    let filePath;

    // Controlled access: whitelist only exact canonical shared assets
    if (sharedFilesWhitelist[urlPath]) {
      filePath = sharedFilesWhitelist[urlPath];
    } else {
      filePath = path.join(
        root,
        urlPath === "/" ? "/index.html" : urlPath,
      );
      // Strictly prevent path traversal outside robot-3d-viewer root
      const normalized = path.normalize(filePath);
      if (!normalized.startsWith(root)) {
        response.writeHead(403);
        response.end("Forbidden");
        return;
      }
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
