FROM alpine:3.20

RUN apk add --no-cache gettext pgbouncer
RUN addgroup -S pgbouncer && adduser -S -G pgbouncer pgbouncer
RUN mkdir -p /etc/pgbouncer && chown -R pgbouncer:pgbouncer /etc/pgbouncer

COPY docker/pgbouncer/entrypoint.sh /entrypoint.sh
COPY docker/pgbouncer/pgbouncer.ini.tmpl /etc/pgbouncer/pgbouncer.ini.tmpl

RUN chmod +x /entrypoint.sh

EXPOSE 6432

USER pgbouncer

ENTRYPOINT ["/entrypoint.sh"]
