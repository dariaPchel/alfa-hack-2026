# Third party components

This project uses the following direct dependencies. Versions are fixed in
`go.mod`/`go.sum` and `package-lock.json`; transitive dependency details
are in those lockfiles. License labels below were read from the installed
module LICENSE files and npm lockfile.

- React 19.3.1 and React DOM 19.3.1 — MIT.
- Vite 8.3.5, @vitejs/plugin-react 6.1.2, Oxlint 1.89.0 — MIT.
- github.com/jackc/pgx/v5 5.7.1 — MIT.
- github.com/redis/go-redis/v9 9.7.0 — BSD 2-Clause.
- github.com/segmentio/kafka-go 0.4.47 — MIT.
- pypdf 6.10.0 is used by the optional research exporter container.
- Tesseract OCR and Poppler tools are installed from Debian packages in the
  optional research exporter. Review their package notices when distributing
  that image.
- PyMuPDF 1.28.2 belongs to the legacy Python pipeline and is not installed
  in the main Compose services.

Runtime container images: postgres:16-alpine, redis:7-alpine,
apache/kafka:3.8.0, golang:1.22-alpine, node:22-alpine,
nginx:1.27-alpine and gcr.io/distroless/static-debian12:nonroot.
Review the image vendor notices for the exact pulled digests before
distribution. No container image is vendored into this repository.
