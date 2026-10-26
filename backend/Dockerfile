FROM golang:1.22-alpine AS build
WORKDIR /src
COPY go.mod go.sum* ./
RUN go mod download
COPY backend ./backend
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o /out/alfa-api ./backend

FROM gcr.io/distroless/static-debian12:nonroot
WORKDIR /app
COPY --from=build /out/alfa-api /app/alfa-api
ENTRYPOINT ["/app/alfa-api"]
