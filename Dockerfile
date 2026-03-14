FROM public.ecr.aws/lambda/python:3.12

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
# システム依存パッケージ（Playwright/Chromium用）
RUN dnf install -y \
    atk \
    at-spi2-atk \
    cups-libs \
    gtk3 \
    libXcomposite \
    libXdamage \
    libXfixes \
    libXrandr \
    libxkbcommon \
    nss \
    pango \
    alsa-lib \
    && dnf clean all

# Pythonライブラリのインストール
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Chromiumブラウザのインストール
RUN playwright install chromium && \
    chmod -R 755 /ms-playwright

# アプリケーションコードのコピー
COPY lambda_function.py ${LAMBDA_TASK_ROOT}/

CMD ["lambda_function.handler"]
