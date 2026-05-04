<!-- Nordeste Agro Clima — Versão definitiva com endpoint real, escala corrigida e recomendações técnicas -->
<div id="na-clima-app">
  <style>
    #na-clima-app {
      --na-green: #087b36;
      --na-green-2: #1a9b4b;
      --na-bg: #f6fbf1;
      --na-card: #ffffff;
      --na-border: #cfe2bf;
      --na-text: #12301c;
      --na-muted: #49624f;
      font-family: Arial, Helvetica, sans-serif;
      color: var(--na-text);
      max-width: 1180px;
      margin: 0 auto;
      padding: 18px;
      background: var(--na-bg);
      border-radius: 18px;
    }
    #na-clima-app * { box-sizing: border-box; }

    .na-header {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      flex-wrap: wrap;
      align-items: center;
      margin-bottom: 16px;
    }
    .na-title h1 {
      margin: 0 0 6px;
      font-size: 28px;
      color: var(--na-green);
      line-height: 1.1;
    }
    .na-title p {
      margin: 0;
      color: var(--na-muted);
      font-size: 14px;
    }

    .na-controls {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
    }
    .na-btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 118px;
      min-height: 42px;
      border: 1px solid #96bd86;
      background: #ffffff !important;
      color: #087b36 !important;
      border-radius: 999px;
      padding: 10px 16px;
      font-weight: 800;
      font-size: 13px;
      line-height: 1;
      cursor: pointer;
      transition: .2s ease;
      text-indent: 0 !important;
      overflow: visible !important;
      box-shadow: 0 4px 16px rgba(0,0,0,.04);
    }
    .na-btn:hover,
    .na-btn.active {
      background: var(--na-green) !important;
      color: #ffffff !important;
      border-color: var(--na-green) !important;
    }

    .na-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 330px;
      gap: 16px;
      align-items: start;
    }

    .na-map-card,
    .na-side-card {
      background: var(--na-card);
      border: 1px solid var(--na-border);
      border-radius: 16px;
      padding: 12px;
      box-shadow: 0 8px 24px rgba(22, 90, 40, .06);
    }

    .na-map-wrap {
      width: 100%;
      min-height: 560px;
      background: #eef7e9;
      border-radius: 14px;
      overflow: hidden;
      border: 1px solid #d8e7ce;
      position: relative;
    }
    #na-map-svg {
      display: block;
      width: 100%;
      height: 600px;
      background: #eef7e9;
    }

    .na-state {
      fill: rgba(255,255,255,0.05);
      stroke: #1f8848;
      stroke-width: 1.2;
      vector-effect: non-scaling-stroke;
    }
    .na-outline {
      fill: none;
      stroke: #0b6b32;
      stroke-width: 1.6;
      vector-effect: non-scaling-stroke;
      opacity: .96;
    }
    .na-point {
      fill: #10351f;
      stroke: #ffffff;
      stroke-width: 1.4;
      vector-effect: non-scaling-stroke;
    }
    .na-label {
      font-size: 10px;
      fill: #12301c;
      font-weight: 800;
      paint-order: stroke;
      stroke: #ffffff;
      stroke-width: 3px;
      stroke-linejoin: round;
    }
    .na-watermark {
      position: absolute;
      left: 24px;
      bottom: 18px;
      background: rgba(246,251,241,.82);
      padding: 5px 8px;
      border-radius: 8px;
      font-size: 12px;
      font-weight: 800;
      color: #063d1b;
    }

    .na-side { display: grid; gap: 10px; }
    .na-side-card h3 {
      margin: 0 0 8px;
      font-size: 16px;
      color: #073d1b;
    }
    .na-side-card p,
    .na-side-card li {
      margin: 6px 0;
      font-size: 12.5px;
      line-height: 1.45;
    }
    .na-side-card ul {
      margin: 8px 0 0 18px;
      padding: 0;
    }
    .na-ok { background: #f2fff3; border-color: #b8dfc0; }
    .na-warning { background: #fff8ea; border-color: #f2d79c; }
    .na-error { background: #fff1f1; border-color: #e8b0b0; }
    .na-tech { background: #f7fbff; border-color: #bcd8ee; }

    .na-legend {
      display: grid;
      grid-template-columns: 1fr;
      gap: 6px;
      font-size: 11px;
    }
    .na-legend-item {
      display: grid;
      grid-template-columns: 54px 1fr;
      gap: 8px;
      align-items: center;
    }
    .na-swatch {
      width: 48px;
      height: 12px;
      border-radius: 4px;
      border: 1px solid rgba(0,0,0,.12);
    }
    .na-legend-note {
      margin-top: 8px;
      padding-top: 8px;
      border-top: 1px solid #dcebd4;
      color: #3b5844;
      font-size: 11px;
      line-height: 1.45;
    }

    .na-loading {
      position: absolute;
      inset: 0;
      display: grid;
      place-items: center;
      background: rgba(246,251,241,.86);
      color: #0b612d;
      font-weight: 800;
      z-index: 3;
      text-align: center;
      padding: 20px;
    }

    @media (max-width: 900px) {
      .na-grid { grid-template-columns: 1fr; }
      #na-map-svg { height: 500px; }
      .na-map-wrap { min-height: 480px; }
    }
  </style>

  <div class="na-header">
    <div class="na-title">
      <h1>Clima Nordeste Agro</h1>
      <p>Mapa de precipitação prevista/modelada com atualização diária pelo WordPress.</p>
    </div>

    <div class="na-controls" aria-label="Selecionar período de previsão">
      <button type="button" class="na-btn active" data-periodo="24h">Previsão 24h</button>
      <button type="button" class="na-btn" data-periodo="48h">Previsão 48h</button>
      <button type="button" class="na-btn" data-periodo="72h">Previsão 72h</button>
    </div>
  </div>

  <div class="na-grid">
    <div class="na-map-card">
      <div class="na-map-wrap">
        <div id="na-loading" class="na-loading">Carregando mapa local e previsão diária...</div>
        <svg id="na-map-svg" viewBox="0 0 1000 760" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Mapa de precipitação prevista Nordeste Agro">
          <defs>
            <clipPath id="na-geo-clip"></clipPath>
          </defs>
          <g id="na-interpolacao" clip-path="url(#na-geo-clip)"></g>
          <g id="na-poligonos"></g>
          <g id="na-pontos"></g>
        </svg>
        <div class="na-watermark">Nordeste Agro • Base local do shapefile</div>
      </div>
    </div>

    <aside class="na-side">
      <div id="na-status" class="na-side-card na-ok">
        <h3>Atualização diária</h3>
        <p><strong>Status:</strong> carregando dados...</p>
      </div>

      <div class="na-side-card">
        <h3>Camada ativa</h3>
        <p><strong id="na-periodo-label">Previsão 24h</strong></p>
        <p id="na-camada-info">Aguardando carregamento.</p>
      </div>

      <div id="na-recomendacao" class="na-side-card na-tech">
        <h3>Recomendações técnicas agrícolas</h3>
        <p>Carregando recomendações...</p>
      </div>

      <div class="na-side-card na-warning">
        <h3>Aviso importante</h3>
        <p>Esta camada mostra <strong>chuva prevista/modelada</strong>, não chuva observada real em estação.</p>
        <p>Use as recomendações como apoio inicial. A decisão final deve considerar estágio da cultura, umidade do solo, previsão local, tipo de solo e orientação técnica.</p>
      </div>

      <div class="na-side-card">
        <h3>Escala de precipitação em mm</h3>
        <div id="na-legend" class="na-legend"></div>
        <div class="na-legend-note">
          Interpretação prática: quanto mais azul/verde, menor volume previsto; amarelo/laranja/vermelho indica maior volume acumulado e maior atenção a operação em campo, erosão, doenças e tráfego de máquinas.
        </div>
      </div>
    </aside>
  </div>

  <script>
    (function () {
      const MAP_URL = "/wp-content/uploads/nordeste-agro/mapas/matopibapa.geojson";
      const API_BASE = "/wp-json/nordeste-agro/v1/previsao-numerica";
      const clip = document.getElementById("na-geo-clip");
      const gPoly = document.getElementById("na-poligonos");
      const gInterp = document.getElementById("na-interpolacao");
      const gPontos = document.getElementById("na-pontos");
      const loading = document.getElementById("na-loading");
      const statusBox = document.getElementById("na-status");
      const camadaInfo = document.getElementById("na-camada-info");
      const periodoLabel = document.getElementById("na-periodo-label");
      const recomendacao = document.getElementById("na-recomendacao");

      let geojson = null;
      let bounds = null;
      let currentPeriodo = "24h";
      const width = 1000;
      const height = 760;
      const padding = 55;

      const escala = [
        [0, 1, "#f3fbff", "0 a 1 mm", "Sem chuva ou chuvisco isolado"],
        [1, 3, "#d8f2ff", "1 a 3 mm", "Chuva muito fraca"],
        [3, 5, "#b9e7ff", "3 a 5 mm", "Chuva fraca"],
        [5, 7, "#8ed6f4", "5 a 7 mm", "Chuva fraca a moderada"],
        [7, 9, "#5fbfdf", "7 a 9 mm", "Moderada baixa"],
        [9, 12, "#38a5c6", "9 a 12 mm", "Moderada"],
        [12, 16, "#38a86b", "12 a 16 mm", "Boa umidade superficial"],
        [16, 20, "#5cc653", "16 a 20 mm", "Boa chuva"],
        [20, 30, "#b8da58", "20 a 30 mm", "Chuva significativa"],
        [30, 40, "#f1db5a", "30 a 40 mm", "Atenção operacional"],
        [40, 50, "#f1b64a", "40 a 50 mm", "Risco moderado"],
        [50, 60, "#ee933a", "50 a 60 mm", "Risco alto"],
        [60, 70, "#e6712d", "60 a 70 mm", "Chuva intensa"],
        [70, 90, "#d64c2d", "70 a 90 mm", "Risco elevado"],
        [90, 125, "#b8322e", "90 a 125 mm", "Risco muito elevado"],
        [125, 200, "#842420", "125 a 200 mm", "Evento extremo"]
      ];

      function colorFor(mm) {
        for (const [min, max, color] of escala) {
          if (mm >= min && mm < max) return color;
        }
        return mm >= 200 ? escala[escala.length - 1][2] : escala[0][2];
      }

      function makeLegend() {
        const el = document.getElementById("na-legend");
        el.innerHTML = escala.map(e =>
          `<div class="na-legend-item"><span class="na-swatch" style="background:${e[2]}"></span><span><strong>${e[3]}</strong> — ${e[4]}</span></div>`
        ).join("");
      }

      function getAllCoords(geom, out = []) {
        if (!geom) return out;
        if (geom.type === "Polygon") {
          geom.coordinates.forEach(ring => ring.forEach(c => out.push(c)));
        } else if (geom.type === "MultiPolygon") {
          geom.coordinates.forEach(poly => poly.forEach(ring => ring.forEach(c => out.push(c))));
        }
        return out;
      }

      function computeBounds(fc) {
        const coords = [];
        fc.features.forEach(f => getAllCoords(f.geometry, coords));
        let minLon = Infinity, maxLon = -Infinity, minLat = Infinity, maxLat = -Infinity;
        coords.forEach(([lon, lat]) => {
          minLon = Math.min(minLon, lon);
          maxLon = Math.max(maxLon, lon);
          minLat = Math.min(minLat, lat);
          maxLat = Math.max(maxLat, lat);
        });
        return { minLon, maxLon, minLat, maxLat };
      }

      function project(lon, lat) {
        const sx = (width - padding * 2) / (bounds.maxLon - bounds.minLon);
        const sy = (height - padding * 2) / (bounds.maxLat - bounds.minLat);
        const s = Math.min(sx, sy);
        const mapW = (bounds.maxLon - bounds.minLon) * s;
        const mapH = (bounds.maxLat - bounds.minLat) * s;
        const offsetX = (width - mapW) / 2;
        const offsetY = (height - mapH) / 2;
        return [
          offsetX + (lon - bounds.minLon) * s,
          offsetY + (bounds.maxLat - lat) * s
        ];
      }

      function pathFromRing(ring) {
        return ring.map(([lon, lat], i) => {
          const [x, y] = project(lon, lat);
          return `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
        }).join(" ") + " Z";
      }

      function geomToPath(geom) {
        if (geom.type === "Polygon") return geom.coordinates.map(pathFromRing).join(" ");
        if (geom.type === "MultiPolygon") return geom.coordinates.flatMap(poly => poly.map(pathFromRing)).join(" ");
        return "";
      }

      function drawGeojson() {
        bounds = computeBounds(geojson);
        gPoly.innerHTML = "";
        clip.innerHTML = "";
        const allClipParts = [];

        geojson.features.forEach(f => {
          const d = geomToPath(f.geometry);
          if (!d) return;
          const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
          path.setAttribute("d", d);
          path.setAttribute("class", "na-state");
          gPoly.appendChild(path);
          allClipParts.push(d);
        });

        const clipPathShape = document.createElementNS("http://www.w3.org/2000/svg", "path");
        clipPathShape.setAttribute("d", allClipParts.join(" "));
        clipPathShape.setAttribute("clip-rule", "evenodd");
        clip.appendChild(clipPathShape);

        const outline = document.createElementNS("http://www.w3.org/2000/svg", "path");
        outline.setAttribute("d", allClipParts.join(" "));
        outline.setAttribute("class", "na-outline");
        gPoly.appendChild(outline);
      }

      function idw(x, y, pts) {
        let num = 0, den = 0;
        const power = 2.25;
        for (const p of pts) {
          const dx = x - p.x;
          const dy = y - p.y;
          const d2 = dx * dx + dy * dy;
          if (d2 < 1) return p.mm;
          const w = 1 / Math.pow(Math.sqrt(d2), power);
          num += w * p.mm;
          den += w;
        }
        return den ? num / den : 0;
      }

      function drawInterpolation(pontos) {
        gInterp.innerHTML = "";
        gPontos.innerHTML = "";

        const pts = pontos.map(p => {
          const [x, y] = project(Number(p.lon), Number(p.lat));
          return { x, y, lat: Number(p.lat), lon: Number(p.lon), mm: Number(p.mm) || 0 };
        });

        const step = pts.length >= 20 ? 9 : 12;

        for (let y = 0; y < height; y += step) {
          for (let x = 0; x < width; x += step) {
            const mm = idw(x + step / 2, y + step / 2, pts);
            const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
            rect.setAttribute("x", x);
            rect.setAttribute("y", y);
            rect.setAttribute("width", step + 1);
            rect.setAttribute("height", step + 1);
            rect.setAttribute("fill", colorFor(mm));
            rect.setAttribute("opacity", "0.74");
            gInterp.appendChild(rect);
          }
        }

        pts.forEach((p, i) => {
          const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
          circle.setAttribute("cx", p.x);
          circle.setAttribute("cy", p.y);
          circle.setAttribute("r", 3.5);
          circle.setAttribute("class", "na-point");
          gPontos.appendChild(circle);

          if (i % 3 === 0 || p.mm >= 35) {
            const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
            text.setAttribute("x", p.x + 6);
            text.setAttribute("y", p.y - 6);
            text.setAttribute("class", "na-label");
            text.textContent = `${p.mm} mm`;
            gPontos.appendChild(text);
          }
        });
      }

      function resumoPontos(pontos) {
        const valores = pontos.map(p => Number(p.mm) || 0);
        const max = Math.max(...valores);
        const min = Math.min(...valores);
        const media = valores.reduce((a,b) => a + b, 0) / valores.length;
        return { min, max, media };
      }

      function gerarRecomendacoes(pontos, periodo) {
        if (!pontos.length) {
          recomendacao.innerHTML = "<h3>Recomendações técnicas agrícolas</h3><p>Sem pontos suficientes para recomendação.</p>";
          return;
        }

        const r = resumoPontos(pontos);
        let nivel = "baixo";
        if (r.max >= 70 || r.media >= 45) nivel = "muito alto";
        else if (r.max >= 50 || r.media >= 35) nivel = "alto";
        else if (r.max >= 30 || r.media >= 22) nivel = "moderado";
        else if (r.max >= 12 || r.media >= 10) nivel = "favorável";

        const recomendacoes = {
          "baixo": [
            "Planejar irrigação suplementar onde houver lavouras em fase crítica e baixa umidade no solo.",
            "Evitar antecipar adubação de cobertura se o solo estiver seco e sem previsão complementar.",
            "Manter monitoramento de estresse hídrico em milho, soja, algodão, feijão e pastagens."
          ],
          "favorável": [
            "Boa condição para germinação, rebrota e desenvolvimento inicial, desde que o solo tenha cobertura adequada.",
            "Avaliar janela para adubação de cobertura, principalmente se houver umidade suficiente para incorporação natural.",
            "Monitorar plantas daninhas, pois chuva leve a moderada favorece novos fluxos de emergência."
          ],
          "moderado": [
            "Revisar operações de pulverização; evitar aplicação antes de chuva forte para reduzir lavagem de produtos.",
            "Acompanhar risco de doenças foliares, principalmente em áreas com maior fechamento de dossel.",
            "Evitar tráfego de máquinas em solo úmido para reduzir compactação."
          ],
          "alto": [
            "Suspender operações de preparo, plantio ou pulverização em áreas com risco de encharcamento.",
            "Verificar drenagem, terraços, carreadores e pontos de erosão antes do evento.",
            "Intensificar monitoramento de doenças e pragas após o período chuvoso."
          ],
          "muito alto": [
            "Priorizar segurança operacional e evitar tráfego de máquinas em áreas suscetíveis a atolamento e compactação.",
            "Monitorar erosão, enxurrada, assoreamento e danos em lavouras recém-implantadas.",
            "Após a chuva, avaliar necessidade de replantio localizado, controle de doenças e reposição nutricional."
          ]
        };

        recomendacao.innerHTML = `
          <h3>Recomendações técnicas agrícolas</h3>
          <p><strong>Período:</strong> Previsão ${periodo}</p>
          <p><strong>Resumo:</strong> mínimo ${r.min.toFixed(1)} mm, média ${r.media.toFixed(1)} mm, máximo ${r.max.toFixed(1)} mm.</p>
          <p><strong>Nível de atenção:</strong> ${nivel.toUpperCase()}.</p>
          <ul>${recomendacoes[nivel].map(item => `<li>${item}</li>`).join("")}</ul>
        `;
      }

      async function loadPeriodo(periodo) {
        currentPeriodo = periodo;
        periodoLabel.textContent = `Previsão ${periodo}`;
        loading.style.display = "grid";
        loading.textContent = `Carregando Previsão ${periodo}...`;

        try {
          const resp = await fetch(`${API_BASE}?periodo=${encodeURIComponent(periodo)}&_=${Date.now()}`, { cache: "no-store" });
          const data = await resp.json();

          if (!data.ok) throw new Error(data.erro || "Resposta inválida do endpoint.");

          const pontos = data.dados && Array.isArray(data.dados.pontos) ? data.dados.pontos : [];
          drawInterpolation(pontos);
          gerarRecomendacoes(pontos, periodo);

          statusBox.className = "na-side-card na-ok";
          statusBox.innerHTML = `
            <h3>Atualização diária</h3>
            <p><strong>Status:</strong> dados reais do endpoint WordPress carregados.</p>
            <p><strong>Recebido no WordPress:</strong> ${data.recebido_em_wordpress || "não informado"}.</p>
            <p><strong>Pontos processados:</strong> ${pontos.length}.</p>
            <p>A página busca o endpoint real do WordPress com cache desativado.</p>
          `;

          camadaInfo.innerHTML = `
            Atualização do modelo: ${data.atualizado_em || "não informado"}.<br>
            Fonte: ${data.fonte || "INMET - Previsão Numérica"}.
          `;
        } catch (err) {
          statusBox.className = "na-side-card na-error";
          statusBox.innerHTML = `<h3>Atualização diária</h3><p><strong>Status:</strong> erro ao carregar endpoint.</p><p>${err.message}</p>`;
          camadaInfo.textContent = "Não foi possível carregar a camada ativa.";
          recomendacao.innerHTML = "<h3>Recomendações técnicas agrícolas</h3><p>Não foi possível gerar recomendações.</p>";
        } finally {
          loading.style.display = "none";
        }
      }

      async function init() {
        makeLegend();
        try {
          const geoResp = await fetch(`${MAP_URL}?_=${Date.now()}`, { cache: "no-store" });
          geojson = await geoResp.json();
          drawGeojson();
          await loadPeriodo(currentPeriodo);
        } catch (err) {
          loading.textContent = "Erro ao carregar o GeoJSON local do mapa. Verifique /wp-content/uploads/nordeste-agro/mapas/matopibapa.geojson";
          statusBox.className = "na-side-card na-error";
          statusBox.innerHTML = `<h3>Erro no mapa</h3><p>${err.message}</p>`;
        }
      }

      document.querySelectorAll(".na-btn").forEach(btn => {
        btn.addEventListener("click", () => {
          document.querySelectorAll(".na-btn").forEach(b => b.classList.remove("active"));
          btn.classList.add("active");
          loadPeriodo(btn.dataset.periodo);
        });
      });

      init();
    })();
  </script>
</div>
