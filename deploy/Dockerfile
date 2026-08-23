# Odoo 19 + the Nepal localisation, as one build artefact (audit finding CI-2).
#
# ============================================================================
# THIS IMAGE HAS NEVER BEEN BUILT.
#
# Docker is not installed on the machine where this was written, so nothing here
# has been executed. Treat it as a reviewed starting point, not a working build:
# the package list, the wkhtmltopdf URL and the requirements install are the three
# things most likely to need adjustment on first contact.
#
# CI-2 stays OPEN until someone has run `docker build` and `docker compose up`
# and a container has served a request. Ticking that gate on the strength of an
# unbuilt Dockerfile would repeat the exact mistake this audit keeps recording:
# FIN-2's reports "worked" until someone rendered one, and TST-5's certificate
# path "worked" until someone called it.
# ============================================================================
#
# Why this exists: dev is Windows with `workers = 0` and production is Linux with
# systemd and multiprocessing, and they share no artefact. They are related by a
# prose table in deploy/README.md, not by anything executable, so "it works on my
# machine" has no meaning here. One image both can run is the fix.

FROM python:3.12-slim-bookworm AS base

# Odoo needs a C toolchain for a few wheels, libpq for psycopg2, and the fonts
# wkhtmltopdf uses. `--no-install-recommends` keeps the image from pulling a
# desktop stack in behind the fonts.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        libxml2-dev \
        libxslt1-dev \
        libldap2-dev \
        libsasl2-dev \
        libjpeg-dev \
        zlib1g-dev \
        libfreetype6-dev \
        libssl-dev \
        node-less \
        fonts-liberation \
        fontconfig \
        xfonts-75dpi \
        xfonts-base \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# wkhtmltopdf, and specifically a **patched-Qt** build. An unpatched build passes
# every smoke test while silently dropping headers and footers from every PDF --
# see DEP-6 and deploy/README.md §1. The version is pinned because the upstream
# packaging repository is archived, so this URL is a fixed target that will
# eventually disappear; when it does, vendor the .deb rather than floating.
ARG WKHTMLTOPDF_VERSION=0.12.6.1-3
ARG WKHTMLTOPDF_DISTRO=bookworm
RUN curl -fsSL -o /tmp/wkhtmltox.deb \
        "https://github.com/wkhtmltopdf/packaging/releases/download/${WKHTMLTOPDF_VERSION}/wkhtmltox_${WKHTMLTOPDF_VERSION}.${WKHTMLTOPDF_DISTRO}_amd64.deb" \
    && apt-get update \
    && apt-get install -y --no-install-recommends /tmp/wkhtmltox.deb \
    && rm -f /tmp/wkhtmltox.deb \
    && rm -rf /var/lib/apt/lists/* \
    # Fail the build now rather than discover it in production: an unpatched build
    # reports its version without "(with patched qt)".
    && wkhtmltopdf --version | grep -q 'with patched qt'

# Odoo must not run as root. The uid is fixed so a bind-mounted filestore has
# predictable ownership.
RUN groupadd -g 10001 odoo && useradd -m -u 10001 -g odoo odoo

WORKDIR /opt/odoo

# Requirements first, so a source change does not invalidate the wheel layer.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# `nepali-datetime` is a hard runtime dependency of nepali_calendar_core and is
# already pinned in requirements.txt (DEP-1). Asserted here because a restore that
# silently lacks it produces a server that boots and then fails on every date.
RUN python -c "import nepali_datetime; print('nepali_datetime', nepali_datetime.__name__)"

COPY --chown=odoo:odoo . /opt/odoo/

# The container's config, not the developer's. odoo.conf is gitignored and holds
# credentials, so it is deliberately NOT copied: it comes from a mount or a
# secret at run time.
ENV ODOO_RC=/etc/odoo/odoo.conf
RUN mkdir -p /etc/odoo /var/lib/odoo && chown -R odoo:odoo /etc/odoo /var/lib/odoo

USER odoo
EXPOSE 8069

# Odoo ships /web/health (web/controllers/home.py), auth='none' and
# save_session=False -- so polling it does not litter the session store, which a
# probe against /web/login would.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8069/web/health', timeout=4).status == 200 else 1)"]

ENTRYPOINT ["python", "-m", "odoo"]
CMD ["--config=/etc/odoo/odoo.conf"]
