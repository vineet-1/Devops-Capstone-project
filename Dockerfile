# Offline-lab PostgreSQL image (official postgres:16-alpine is used outside the lab).
# Same contract as the official image: POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB / PGDATA.
ARG PG_BASE=capstone/ubuntu-postgres:16-base
FROM ${PG_BASE}
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 755 /usr/local/bin/docker-entrypoint.sh && mkdir -p /var/run/postgresql && chown -R postgres:postgres /var/run/postgresql
USER postgres
ENV PGDATA=/var/lib/postgresql/data/pgdata
EXPOSE 5432
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["postgres"]
