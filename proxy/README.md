This directory contains the nginx reverse proxy configuration used by docker-compose.

- nginx.conf: Routes / to the frontend container and /api/ to the backend (web) container.

If you run docker-compose up, the proxy will listen on host port 80 and forward traffic appropriately.

On Windows, ensure Docker Desktop exposes ports 80 and 443, or change the port mappings in docker-compose.yml.
