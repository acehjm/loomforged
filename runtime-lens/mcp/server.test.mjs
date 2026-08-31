import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync, readFileSync, realpathSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  buildDiscoveryScript,
  buildInspectionScript,
  buildProcessInspectionScript,
  buildPortInspectionScript,
  buildRuntimeInspectionScript,
  buildSearchBody,
  extractRemoteStage,
  inspectPort,
  inspectProcess,
  inspectService,
  listLogDirectory,
  parsePortInspectionOutput,
  parseDiscoveryOutput,
  parseInspectionOutput,
  readServiceConfig,
  resolveNginxRoute,
  searchLogs,
  searchJournal,
  traceRequest,
  validateConfig,
} from "./server.mjs";

const rules = JSON.parse(
  readFileSync(new URL("../config/runtime-lens.rules.json", import.meta.url), "utf8"),
);

function makeRule() {
  const template = rules.pathTemplates[0];
  return {
    ...template,
    componentPattern: "*.[0-9]*",
    templateMode: "component-instance",
  };
}

function makeHost(root) {
  return { readableRoots: [root] };
}

function runShell(script) {
  return execFileSync("sh", ["-s"], {
    input: script,
    encoding: "utf8",
    stdio: ["pipe", "pipe", "pipe"],
  });
}

function withFixture(run) {
  const root = mkdtempSync(path.join(tmpdir(), "runtime-lens-test-"));
  try {
    return run(root);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

async function withFixtureAsync(run) {
  const root = mkdtempSync(path.join(tmpdir(), "runtime-lens-test-"));
  try {
    return await run(root);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

function makeConfig(root, additionalRoots = []) {
  const platformRoots = [root, ...additionalRoots].map(item => realpathSync(item));
  root = platformRoots[0];
  return validateConfig({
    connections: {
      version: 1,
      connections: [{ ip: "192.0.2.20", port: 22, username: "test", password: "test" }],
    },
    rules: {
      version: 1,
      platformRoots,
      pathTemplates: [{
        id: "business-services",
        category: "business",
        componentPath: "{platformRoot}/components/{component}.{N}",
        configPatterns: ["conf/*", "bin/{service}/*"],
        logPatterns: [
          "logs/{component}.{service}.*.log",
          "logs/{component}.{service}.*.log.[0-9]*",
          "logs/*.log",
          "logs/*.log.[0-9]*",
          "logs/{service}/*.log",
          "logs/{service}/*.log.[0-9]*",
          "logs/{service}/{component}.{service}.*.log",
          "logs/{service}/{component}.{service}.*.log.[0-9]*",
        ],
        startScriptPatterns: ["script/{service}/*.sh"],
        installationFailurePatterns: ["{component}.{N}.faild/*"],
        tomcat: {
          componentPattern: "tomcat*",
          deploymentPatterns: ["webapps/{component}", "webapps/{service}"],
          logPatterns: [
            "logs/{component}/{service}/*.log",
            "logs/{component}/{service}/*.log.[0-9]*",
            "logs/{component}/{component}.{service}.*.log",
            "logs/{component}/{component}.{service}.*.log.[0-9]*",
          ],
        },
      }],
      nginx: { configRoots: [], accessLogs: [], errorLogs: [] },
      installationLogs: ["{platformRoot}/installation/global.log"],
      traceSearch: { roots: ["{platformRoot}/components"], filePatterns: ["*.log"], maxDepth: 6 },
      serviceAliases: {},
    },
  });
}

async function localRunner(_config, _host, script) {
  return { stdout: runShell(script), stderr: "" };
}

function inspect(root, component, service, fileLimit = 20) {
  const output = runShell(
    buildInspectionScript(makeHost(root), makeRule(), root, component, service, fileLimit),
  );
  return parseInspectionOutput(output, {
    environment: "test",
    host: "host",
    rule: { id: "business-services", category: "business" },
    component,
    service,
  });
}

test("service-only lookup resolves a service nested under a differently named component", () =>
  withFixture(root => {
    const serviceDir = path.join(root, "billing.1", "bin", "orders");
    mkdirSync(serviceDir, { recursive: true });
    writeFileSync(path.join(serviceDir, "application.properties"), "server.port=8083\n");

    const result = inspect(root, "", "orders");

    assert.deepEqual(result.components.map(item => item.component), ["billing"]);
    assert.ok(result.configs.some(item => item.endsWith("/bin/orders/application.properties")));
  }),
);

test("known component lookup is not dropped by an unrelated discovery cap", () =>
  withFixture(root => {
    for (let index = 0; index < 105; index++) {
      mkdirSync(path.join(root, `component${String(index).padStart(3, "0")}.1`));
    }
    mkdirSync(path.join(root, "zzztarget.1"));

    const result = inspect(root, "zzztarget", "orders");

    assert.deepEqual(result.components.map(item => item.component), ["zzztarget"]);
  }),
);

test("queried discovery does not apply the output cap before query filtering", () =>
  withFixture(root => {
    for (let index = 0; index < 8; index++) {
      mkdirSync(path.join(root, `component${String(index).padStart(2, "0")}.1`));
    }
    mkdirSync(path.join(root, "zzztarget.1"));

    const output = runShell(
      buildDiscoveryScript(makeHost(root), makeRule(), root, 5, 20, true),
    );
    const services = parseDiscoveryOutput(output, {
      environment: "test",
      host: "host",
      rule: makeRule(),
      aliases: () => [],
    });

    assert.ok(services.some(item => item.component === "zzztarget"));
  }),
);

test("service-specific log names are selected before generic files", () =>
  withFixture(root => {
    const logsDir = path.join(root, "billing.1", "logs");
    mkdirSync(logsDir, { recursive: true });
    for (let index = 0; index < 25; index++) {
      writeFileSync(path.join(logsDir, `000-noise-${String(index).padStart(2, "0")}.log`), "noise\n");
    }
    const target = path.join(logsDir, "billing.orders.error.log");
    writeFileSync(target, "ERROR\n");

    const result = inspect(root, "billing", "orders", 20);

    assert.ok(result.logs.some(item => item.endsWith("/billing.1/logs/billing.orders.error.log")));
  }),
);

test("rotated service logs remain discoverable without a trace ID", () =>
  withFixture(root => {
    const logsDir = path.join(root, "billing.1", "logs");
    mkdirSync(logsDir, { recursive: true });
    writeFileSync(path.join(logsDir, "billing.orders.debug.log.1"), "15:00 DEBUG scheduled task\n");

    const result = inspect(root, "billing", "orders", 20);

    assert.ok(result.logs.some(item => item.endsWith("/billing.1/logs/billing.orders.debug.log.1")));
  }),
);

test("Tomcat deployment can use the component name when service differs", () =>
  withFixture(root => {
    const deploymentDir = path.join(root, "tomcat85linux64.2", "webapps", "logservice");
    mkdirSync(deploymentDir, { recursive: true });

    const result = inspect(root, "logservice", "log");

    assert.deepEqual(result.deployments.map(item => item.deploymentPath), [realpathSync(deploymentDir)]);
  }),
);

test("component-only log search automatically continues when one strong service is found", async () =>
  withFixtureAsync(async root => {
    const componentRoot = path.join(root, "components", "acme.1");
    mkdirSync(path.join(componentRoot, "logs"), { recursive: true });
    mkdirSync(path.join(componentRoot, "bin", "helper"), { recursive: true });
    writeFileSync(path.join(componentRoot, "logs", "acme.orders.error.log"), "15:00 ERROR remote call failed\n");
    writeFileSync(path.join(componentRoot, "bin", "helper", "helper.conf"), "enabled=true\n");

    const result = await searchLogs(makeConfig(root), {
      environment: "192.0.2.20",
      scope: "service",
      component: "acme",
      query: "ERROR",
    }, localRunner);

    assert.equal(result.resolvedService, "orders");
    assert.equal(result.requiresServiceSelection, false);
    assert.equal(result.matches.length, 1);
    assert.match(result.matches[0].text, /remote call failed/);
  }),
);

test("known component log discovery expands direct paths without find", async () =>
  withFixtureAsync(async root => {
    const logsDir = path.join(root, "components", "screening.1", "logs", "opslog");
    mkdirSync(logsDir, { recursive: true });
    writeFileSync(path.join(logsDir, "screening.opslog.debug.log"), "12:00 completed\n");
    const focusedRunner = async (_config, _host, script) => {
      if (/\bfind\s/.test(script)) throw new Error("component discovery traversed with find");
      return { stdout: runShell(script), stderr: "" };
    };

    const result = await searchLogs(makeConfig(root), {
      environment: "192.0.2.20",
      scope: "service",
      component: "screening",
      timeHint: "12:00",
    }, focusedRunner);

    assert.equal(result.queryStatus, "complete");
    assert.equal(result.resolvedService, "opslog");
    assert.equal(result.matches.length, 1);
  }),
);

test("component and service identifiers are normalized to lowercase", async () =>
  withFixtureAsync(async root => {
    const logsDir = path.join(root, "components", "esc.1", "logs");
    mkdirSync(logsDir, { recursive: true });
    writeFileSync(path.join(logsDir, "esc.eds.error.log"), "ERROR event dispatch failed\n");

    const result = await searchLogs(makeConfig(root), {
      environment: "192.0.2.20",
      scope: "service",
      component: "ESC",
      service: "EDS",
      query: "ERROR",
    }, localRunner);

    assert.equal(result.component, "esc");
    assert.equal(result.requestedService, "EDS");
    assert.equal(result.resolvedService, "eds");
    assert.equal(result.matches.length, 1);
    assert.match(result.matches[0].text, /event dispatch failed/);
  }),
);

test("known component and service log search bypasses runtime inspection", async () =>
  withFixtureAsync(async root => {
    const logsDir = path.join(root, "components", "screening.1", "logs", "opslog");
    mkdirSync(logsDir, { recursive: true });
    writeFileSync(
      path.join(logsDir, "screening.opslog.debug.log"),
      "2026-08-19 12:00 installation completed\n",
    );
    const scripts = [];
    const focusedRunner = async (_config, _host, script) => {
      scripts.push(script);
      if (/\/proc\/\[0-9\]|systemctl|inspect-processes|\bfind\s/.test(script)) {
        throw new Error("broad runtime inspection was used for a focused log search");
      }
      return { stdout: runShell(script), stderr: "" };
    };

    const result = await searchLogs(makeConfig(root), {
      environment: "192.0.2.20",
      scope: "service",
      component: "screening",
      service: "opslog",
      timeHint: "2026-08-19 12:00",
    }, focusedRunner);

    assert.equal(result.queryStatus, "complete");
    assert.equal(result.matches.length, 1);
    assert.equal(scripts.some(script => /\/proc\/\[0-9\]|systemctl|inspect-processes|\bfind\s/.test(script)), false);
    assert.equal(scripts.some(script => script.includes("locate-service-logs")), true);
    assert.equal(scripts.some(script => script.includes("search-log-content")), true);
  }),
);

test("component-only search discovers a service from its log subdirectory", async () =>
  withFixtureAsync(async root => {
    const componentLogsDir = path.join(root, "components", "screening.1", "logs");
    const logsDir = path.join(componentLogsDir, "opslog");
    mkdirSync(logsDir, { recursive: true });
    for (let index = 0; index < 25; index++) {
      writeFileSync(
        path.join(componentLogsDir, `generic-${String(index).padStart(2, "0")}.log`),
        "unrelated\n",
      );
    }
    writeFileSync(
      path.join(logsDir, "screening.opslog.error.log"),
      "ERROR opslog request failed\n",
    );

    const result = await searchLogs(makeConfig(root), {
      environment: "192.0.2.20",
      scope: "service",
      component: "screening",
      query: "ERROR",
    }, localRunner);

    assert.equal(result.resolvedService, "opslog");
    assert.equal(result.requiresServiceSelection, false);
    assert.equal(result.matches.length, 1);
    assert.match(result.matches[0].path, /screening\.1\/logs\/opslog\//);
  }),
);

test("component-only discovery ignores an archive directory beside a real Tomcat service", async () =>
  withFixtureAsync(async root => {
    const componentLogRoot = path.join(root, "components", "tomcat85.1", "logs", "acme");
    const serviceLogRoot = path.join(componentLogRoot, "orders");
    const archiveLogRoot = path.join(componentLogRoot, "old_log");
    mkdirSync(serviceLogRoot, { recursive: true });
    mkdirSync(archiveLogRoot, { recursive: true });
    writeFileSync(path.join(serviceLogRoot, "acme.orders.error.log"), "ERROR current\n");
    writeFileSync(path.join(archiveLogRoot, "acme.orders.error.log.1"), "ERROR archived\n");

    const result = await searchLogs(makeConfig(root), {
      environment: "192.0.2.20",
      scope: "service",
      component: "acme",
      query: "ERROR",
    }, localRunner);

    assert.equal(result.resolvedService, "orders");
    assert.equal(result.requiresServiceSelection, false);
    assert.deepEqual(result.serviceCandidates.map(item => item.service), ["orders"]);
    assert.equal(result.serviceCandidates.some(item => item.service === "old_log"), false);
  }),
);

test("Tomcat logs directly under the component directory are searchable", async () =>
  withFixtureAsync(async root => {
    const componentLogRoot = path.join(root, "components", "tomcat85.1", "logs", "acme");
    mkdirSync(componentLogRoot, { recursive: true });
    writeFileSync(path.join(componentLogRoot, "acme.orders.error.log"), "ERROR direct layout\n");

    const result = await searchLogs(makeConfig(root), {
      environment: "192.0.2.20",
      scope: "service",
      component: "acme",
      service: "orders",
      query: "ERROR",
    }, localRunner);

    assert.equal(result.resolvedService, "orders");
    assert.equal(result.matches.length, 1);
    assert.match(result.matches[0].path, /tomcat85\.1\/logs\/acme\/acme\.orders\.error\.log$/);
  }),
);

test("component-only search infers a service from a direct Tomcat log filename", async () =>
  withFixtureAsync(async root => {
    const componentLogRoot = path.join(root, "components", "tomcat85.1", "logs", "acme");
    mkdirSync(componentLogRoot, { recursive: true });
    writeFileSync(path.join(componentLogRoot, "acme.orders.debug.log"), "DEBUG direct layout\n");

    const result = await searchLogs(makeConfig(root), {
      environment: "192.0.2.20",
      scope: "service",
      component: "acme",
      query: "DEBUG",
    }, localRunner);

    assert.equal(result.resolvedService, "orders");
    assert.deepEqual(result.serviceCandidates.map(item => item.service), ["orders"]);
    assert.equal(result.matches.length, 1);
  }),
);

test("component-only log search returns choices when multiple services are found", async () =>
  withFixtureAsync(async root => {
    const logsDir = path.join(root, "components", "acme.1", "logs");
    mkdirSync(logsDir, { recursive: true });
    writeFileSync(path.join(logsDir, "acme.orders.error.log"), "ERROR orders\n");
    writeFileSync(path.join(logsDir, "acme.billing.error.log"), "ERROR billing\n");

    const result = await searchLogs(makeConfig(root), {
      environment: "192.0.2.20",
      scope: "service",
      component: "acme",
      query: "ERROR",
    }, localRunner);

    assert.equal(result.requiresServiceSelection, true);
    assert.deepEqual(result.serviceCandidates.map(item => item.service), ["billing", "orders"]);
    assert.equal(result.searchedFiles, 0);
  }),
);

test("the same service across component instances is queried without asking", async () =>
  withFixtureAsync(async root => {
    for (const instance of ["1", "2"]) {
      const logsDir = path.join(root, "components", `acme.${instance}`, "logs");
      mkdirSync(logsDir, { recursive: true });
      writeFileSync(path.join(logsDir, "acme.orders.error.log"), `ERROR instance ${instance}\n`);
    }

    const result = await searchLogs(makeConfig(root), {
      environment: "192.0.2.20",
      scope: "service",
      component: "acme",
      query: "ERROR",
    }, localRunner);

    assert.equal(result.resolvedService, "orders");
    assert.equal(result.requiresServiceSelection, false);
    assert.equal(result.matches.length, 2);
  }),
);

test("service log limits preserve evidence from every component instance", async () =>
  withFixtureAsync(async root => {
    for (const instance of ["1", "2"]) {
      const logsDir = path.join(root, "components", `acme.${instance}`, "logs");
      mkdirSync(logsDir, { recursive: true });
      for (let index = 0; index < 15; index++) {
        writeFileSync(path.join(logsDir, `acme.orders.level${String(index).padStart(2, "0")}.log`), `ERROR instance ${instance} file ${index}\n`);
      }
    }

    const result = await searchLogs(makeConfig(root), {
      environment: "192.0.2.20",
      scope: "service",
      component: "acme",
      service: "orders",
      query: "ERROR",
      lines: 10,
    }, localRunner);

    assert.equal(result.targetDiscoveryTruncated, true);
    assert.equal(result.requestedTargets, 20);
    assert.ok(result.matches.some(item => item.path.includes("/acme.1/")));
    assert.ok(result.matches.some(item => item.path.includes("/acme.2/")));
  }),
);

test("component installation search combines sibling faild logs with public installation logs", async () =>
  withFixtureAsync(async root => {
    const failureDir = path.join(root, "components", "ckks.1.faild");
    const publicDir = path.join(root, "installation");
    mkdirSync(failureDir, { recursive: true });
    mkdirSync(publicDir, { recursive: true });
    writeFileSync(path.join(failureDir, "installer.log"), "15:00 FAILED dependency check\n");
    writeFileSync(path.join(publicDir, "global.log"), "15:00 FAILED install task ckks\n");
    const focusedRunner = async (_config, _host, script) => {
      if (/\bfind\s/.test(script)) throw new Error("known component installation lookup traversed with find");
      return { stdout: runShell(script), stderr: "" };
    };

    const result = await searchLogs(makeConfig(root), {
      environment: "192.0.2.20",
      scope: "installation",
      component: "ckks",
      query: "FAILED",
    }, focusedRunner);

    assert.equal(result.matches.length, 2);
    assert.ok(result.matches.some(item => item.path.endsWith("/ckks.1.faild/installer.log")));
    assert.ok(result.matches.some(item => item.path.endsWith("/installation/global.log")));
  }),
);

test("matchAll accepts terms appearing within the configured context window", () =>
  withFixture(root => {
    const logPath = path.join(root, "service.log");
    writeFileSync(logPath, "trace-123\nrequest details\nERROR upstream failed\n");
    const body = buildSearchBody(["trace-123", "ERROR"], { lines: 20, context: 3 }, { matchAll: true });

    const output = runShell(`resolved_path=${JSON.stringify(logPath)}\n${body}\n`);

    assert.match(output, /trace-123/);
    assert.match(output, /ERROR upstream failed/);
  }),
);

test("approximate time hints constrain content without becoming OR search terms", async () =>
  withFixtureAsync(async root => {
    const logPath = path.join(root, "components", "acme.1", "logs", "acme.orders.error.log");
    mkdirSync(path.dirname(logPath), { recursive: true });
    writeFileSync(logPath, [
      "2026-08-21 09:30:00 ERROR outside early",
      "2026-08-21 10:50:00 ERROR near requested window",
      "2026-08-21 11:30:00 ERROR inside requested window",
      "2026-08-21 12:10:00 ERROR near requested window end",
      "2026-08-21 13:30:00 ERROR outside late",
    ].join("\n"));

    const result = await searchLogs(makeConfig(root), {
      environment: "192.0.2.20",
      host: "server",
      path: realpathSync(logPath),
      query: "ERROR",
      timeHint: "2026-08-21 11:00 到 12:00 左右",
      context: 1,
      lines: 50,
    }, localRunner);

    assert.equal(result.timeHintStatus, "applied");
    assert.equal(result.searchedFiles, 1);
    assert.match(result.matches[0].text, /10:50:00/);
    assert.match(result.matches[0].text, /11:30:00/);
    assert.match(result.matches[0].text, /12:10:00/);
    assert.doesNotMatch(result.matches[0].text, /09:30:00/);
    assert.doesNotMatch(result.matches[0].text, /13:30:00/);
    assert.deepEqual(result.contentTerms, ["ERROR"]);
  }),
);

test("structured approximate time accepts a loose user range", async () =>
  withFixtureAsync(async root => {
    const logPath = path.join(root, "components", "acme.1", "logs", "acme.orders.error.log");
    mkdirSync(path.dirname(logPath), { recursive: true });
    writeFileSync(logPath, [
      "2026-08-21 10:20:00 ERROR too early",
      "2026-08-21 10:42:50 ERROR near approximate range",
      "2026-08-21 11:30:00 ERROR inside range",
      "2026-08-21 12:40:00 ERROR too late",
    ].join("\n"));

    const result = await searchLogs(makeConfig(root), {
      environment: "192.0.2.20",
      host: "server",
      path: realpathSync(logPath),
      query: "ERROR",
      time: {
        date: "2026-08-21",
        start: "11:00",
        end: "12:00",
        precision: "approximate",
      },
      lines: 50,
    }, localRunner);

    assert.equal(result.timeHintStatus, "applied");
    assert.match(result.matches[0].text, /10:42:50/);
    assert.match(result.matches[0].text, /11:30:00/);
    assert.doesNotMatch(result.matches[0].text, /10:20:00/);
    assert.doesNotMatch(result.matches[0].text, /12:40:00/);
  }),
);

test("an empty query result distinguishes data in the window from no window data", async () =>
  withFixtureAsync(async root => {
    const logPath = path.join(root, "components", "acme.1", "logs", "acme.orders.error.log");
    mkdirSync(path.dirname(logPath), { recursive: true });
    writeFileSync(logPath, "2026-08-21 11:30:00 INFO request completed\n");

    const result = await searchLogs(makeConfig(root), {
      environment: "192.0.2.20",
      host: "server",
      path: realpathSync(logPath),
      query: "ERROR",
      time: { date: "2026-08-21", start: "11:00", end: "12:00", precision: "approximate" },
    }, localRunner);

    assert.equal(result.matches.length, 0);
    assert.equal(result.searchOutcome, "no-query-match-in-window");
    assert.equal(result.timeDiagnostics[0].inWindowLines, 1);
    assert.equal(result.timeDiagnostics[0].matchedLines, 0);
  }),
);

test("a query miss reports the nearest matching record outside the approximate window", async () =>
  withFixtureAsync(async root => {
    const logPath = path.join(root, "components", "acme.1", "logs", "acme.orders.error.log");
    mkdirSync(path.dirname(logPath), { recursive: true });
    writeFileSync(logPath, [
      "2026-08-21 10:28:00 ERROR nearest before",
      "2026-08-21 11:30:00 INFO request completed",
      "2026-08-21 12:40:00 INFO request completed",
    ].join("\n"));

    const result = await searchLogs(makeConfig(root), {
      environment: "192.0.2.20",
      host: "server",
      path: realpathSync(logPath),
      query: "ERROR",
      time: { date: "2026-08-21", start: "11:00", end: "12:00", precision: "approximate" },
    }, localRunner);

    assert.equal(result.searchOutcome, "no-query-match-in-window");
    assert.equal(result.timeDiagnostics[0].nearest.before.timestamp, "2026-08-21 10:28:00");
    assert.equal(result.timeDiagnostics[0].nearest.before.distanceMinutes, 2);
  }),
);

test("bounded log results report latest ordering and truncation", async () =>
  withFixtureAsync(async root => {
    const logPath = path.join(root, "components", "acme.1", "logs", "acme.orders.error.log");
    mkdirSync(path.dirname(logPath), { recursive: true });
    writeFileSync(logPath, [1, 2, 3, 4, 5].map(index => `ERROR event ${index}`).join("\n"));

    const result = await searchLogs(makeConfig(root), {
      environment: "192.0.2.20",
      host: "server",
      path: realpathSync(logPath),
      query: "ERROR",
      context: 1,
      lines: 2,
    }, localRunner);

    assert.equal(result.resultOrder, "latest");
    assert.equal(result.truncated, true);
    assert.equal(result.returnedLines, 2);
    assert.match(result.matches[0].text, /event 5/);
    assert.doesNotMatch(result.matches[0].text, /event 1/);
  }),
);

test("read_service_config does not count a directory as a searched file", async () =>
  withFixtureAsync(async root => {
    const configDir = path.join(root, "components", "acme.1", "conf");
    mkdirSync(configDir, { recursive: true });
    writeFileSync(path.join(configDir, "application.properties"), "server.port=8080\n");

    const result = await readServiceConfig(makeConfig(root), {
      environment: "192.0.2.20",
      host: "server",
      path: realpathSync(configDir),
      query: "server.port",
    }, localRunner);

    assert.equal(result.requestedTargets, 1);
    assert.equal(result.searchedFiles, 0);
    assert.deepEqual(result.skippedTargets.map(item => item.reason), ["not-regular-file"]);
  }),
);

test("an evidenced list of exact log files is searched in one call", async () =>
  withFixtureAsync(async root => {
    const logsDir = path.join(root, "components", "acme.1", "logs", "worker");
    mkdirSync(logsDir, { recursive: true });
    const first = path.join(logsDir, "worker-error.log");
    const second = path.join(logsDir, "worker-debug.log");
    writeFileSync(first, "ERROR first file\n");
    writeFileSync(second, "ERROR second file\n");

    const result = await searchLogs(makeConfig(root), {
      environment: "192.0.2.20",
      host: "server",
      paths: [realpathSync(first), realpathSync(second)],
      query: "ERROR",
    }, localRunner);

    assert.equal(result.requestedTargets, 2);
    assert.equal(result.searchedFiles, 2);
    assert.equal(result.matches.length, 2);
  }),
);

test("compressed logs are reported as unsupported instead of searched empty", async () =>
  withFixtureAsync(async root => {
    const logPath = path.join(root, "components", "acme.1", "logs", "acme.orders.error.log.gz");
    mkdirSync(path.dirname(logPath), { recursive: true });
    writeFileSync(logPath, "compressed fixture placeholder\n");

    const result = await searchLogs(makeConfig(root), {
      environment: "192.0.2.20",
      host: "server",
      path: realpathSync(logPath),
      query: "ERROR",
    }, localRunner);

    assert.equal(result.searchedFiles, 0);
    assert.deepEqual(result.skippedTargets.map(item => item.reason), ["unsupported-file-format"]);
  }),
);

test("trace_request uses focused service logs when identifiers are known", async () =>
  withFixtureAsync(async root => {
    const logPath = path.join(root, "components", "acme.1", "logs", "acme.orders.debug.log");
    mkdirSync(path.dirname(logPath), { recursive: true });
    writeFileSync(logPath, "trace-123 request completed\n");
    const runner = async (_config, _host, script, overrides = {}) => {
      assert.doesNotMatch(script, /find \"\$resolved_path\" -maxdepth 6/);
      assert.equal(overrides.timeoutMs, 20000);
      return { stdout: runShell(script), stderr: "" };
    };

    const result = await traceRequest(makeConfig(root), {
      environment: "192.0.2.20",
      host: "server",
      component: "acme",
      service: "orders",
      traceId: "trace-123",
    }, runner);

    assert.equal(result.traceMode, "service-scoped");
    assert.equal(result.searchOutcome, "matched");
  }),
);

test("nginx route search is shallow, bounded, and de-duplicates equivalent blocks", async () =>
  withFixtureAsync(async root => {
    const configRoot = path.join(root, "nginx");
    mkdirSync(configRoot, { recursive: true });
    const route = "location /proxy {\n  proxy_pass http://127.0.0.1:8080;\n}\n";
    writeFileSync(path.join(configRoot, "proxy_http.conf"), route);
    writeFileSync(path.join(configRoot, "proxy_https.conf"), route);
    const config = makeConfig(root);
    config.environments["192.0.2.20"].hosts.server.nginx.configRoots = [realpathSync(configRoot)];
    const calls = [];

    const result = await resolveNginxRoute(config, {
      environment: "192.0.2.20",
      host: "server",
      needle: "proxy_pass",
      context: 2,
    }, async (_config, _host, script, overrides = {}) => {
      calls.push({ script, overrides });
      return { stdout: runShell(script), stderr: "" };
    });

    assert.match(calls[0].script, /-maxdepth 2/);
    assert.doesNotMatch(calls[0].script, /-maxdepth 6/);
    assert.equal(calls[0].overrides.timeoutMs, 20000);
    assert.equal(result.queryStatus, "complete");
    assert.equal(result.matches.length, 1);
    assert.equal(result.duplicateBlocks, 1);
  }),
);

test("an unparsed time hint is reported and does not suppress content evidence", async () =>
  withFixtureAsync(async root => {
    const logPath = path.join(root, "components", "acme.1", "logs", "acme.orders.error.log");
    mkdirSync(path.dirname(logPath), { recursive: true });
    writeFileSync(logPath, "2026-08-21 11:30:00 ERROR retained\n");

    const result = await searchLogs(makeConfig(root), {
      environment: "192.0.2.20",
      host: "server",
      path: realpathSync(logPath),
      query: "ERROR",
      timeHint: "午饭前后那一阵",
    }, localRunner);

    assert.equal(result.timeHintStatus, "unparsed");
    assert.equal(result.matches.length, 1);
    assert.match(result.matches[0].text, /ERROR retained/);
    assert.ok(result.warnings.some(item => item.timeHintStatus === "unparsed"));
  }),
);

test("unsupported log timestamps preserve content matches and report the limitation", async () =>
  withFixtureAsync(async root => {
    const logPath = path.join(root, "components", "acme.1", "logs", "acme.orders.error.log");
    mkdirSync(path.dirname(logPath), { recursive: true });
    writeFileSync(logPath, "Aug 21 11:30:00 ERROR retained without supported timestamp\n");

    const result = await searchLogs(makeConfig(root), {
      environment: "192.0.2.20",
      host: "server",
      path: realpathSync(logPath),
      query: "ERROR",
      timeHint: "2026-08-21 11:00 到 12:00 左右",
    }, localRunner);

    assert.equal(result.timeHintStatus, "unsupported");
    assert.equal(result.matches.length, 1);
    assert.match(result.matches[0].text, /ERROR retained/);
    assert.ok(result.warnings.some(item => item.unsupportedFiles === 1));
  }),
);

test("an explicit directory is skipped instead of being counted as a searched file", async () =>
  withFixtureAsync(async root => {
    const logsDir = path.join(root, "components", "acme.1", "logs");
    mkdirSync(logsDir, { recursive: true });
    writeFileSync(path.join(logsDir, "acme.orders.error.log"), "ERROR should not be read recursively\n");

    const result = await searchLogs(makeConfig(root), {
      environment: "192.0.2.20",
      host: "server",
      path: realpathSync(logsDir),
      query: "ERROR",
    }, localRunner);

    assert.equal(result.requestedTargets, 1);
    assert.equal(result.searchedFiles, 0);
    assert.equal(result.matches.length, 0);
    assert.deepEqual(result.skippedTargets.map(item => item.reason), ["not-regular-file"]);
  }),
);

test("service log search supports nonstandard file names inside a service directory", async () =>
  withFixtureAsync(async root => {
    const logsDir = path.join(root, "components", "acme.1", "logs", "worker");
    mkdirSync(logsDir, { recursive: true });
    writeFileSync(path.join(logsDir, "runtime-error.log"), "ERROR independent process failed\n");

    const result = await searchLogs(makeConfig(root), {
      environment: "192.0.2.20",
      scope: "service",
      component: "acme",
      service: "worker",
      query: "ERROR",
    }, localRunner);

    assert.equal(result.searchedFiles, 1);
    assert.equal(result.matches.length, 1);
    assert.match(result.matches[0].path, /logs\/worker\/runtime-error\.log$/);
  }),
);

test("strong runtime evidence suppresses unrelated service-text process matches", () => {
  const output = [
    "PROCESS\t13165\t1\ttomcat-webapp\t/opt/hikvision/web/components/tomcat85linux64.2\t/java\t\tjava org.apache.catalina.startup.Bootstrap",
    "PROCESS\t1763\t1\tservice-text\t/opt/hikvision/web/components/logservice.1\t/postgres\t\tpostgres logservice_logdb_user",
  ].join("\n");

  const result = parseInspectionOutput(output, {
    environment: "test",
    host: "host",
    rule: { id: "business-services", category: "business" },
    component: "",
    service: "logservice",
  });

  assert.deepEqual(result.runtimeInstances.map(item => item.pid), [13165]);
  assert.equal(result.runtimeInstances[0].matchConfidence, "strong");
});

test("service process matching accepts architecture suffixes", () =>
  withFixture(root => {
    const script = buildInspectionScript(
      makeHost(root),
      makeRule(),
      root,
      "screening",
      "opslog",
      20,
    );
    const match = script.match(/grep -E -q -- '\(([^']+)\)'/);
    assert.ok(match, "service process regular expression should be present");
    assert.equal(new RegExp(`(${match[1]})`).test("/opt/app/opslog_x86.upx"), true);
  }),
);

test("runtime inspection filters one ps snapshot instead of walking every proc entry", () => {
  const script = buildRuntimeInspectionScript("acme", "orders");

  assert.match(script, /ps -eo pid=,ppid=,args=/);
  assert.doesNotMatch(script, /for proc_path in \/proc\/\[0-9\]\*/);
  assert.match(script, /service_filter=/);
  assert.match(script, /component_filter=/);
});

test("runtime inspection prefers a discovered Tomcat path over a broad service token", () => {
  const tomcatPath = "/opt/hikvision/web/components/tomcat85linux64.2";
  const script = buildRuntimeInspectionScript("logservice", "log", [tomcatPath]);

  assert.match(script, new RegExp(tomcatPath.replaceAll("/", "\\/")));
  assert.match(script, /match_reason="tomcat-path"/);
  assert.doesNotMatch(script, /\[\^A-Za-z0-9\]\)log\(\[\^A-Za-z0-9\]/);
});

test("port inspection uses the exact listening port and returns bounded runtime evidence", async () =>
  withFixtureAsync(async root => {
    const scripts = [];
    const result = await inspectPort(makeConfig(root), {
      environment: "192.0.2.20",
      port: 6040,
    }, async (_config, _host, script, overrides = {}) => {
      scripts.push({ script, overrides });
      return {
        stdout: [
          "PORT_SOCKET\t13165\tLISTEN 0 1000 :::6040 :::* users:((java,pid=13165,fd=41))",
          "PORT_PROCESS\t13165\t/opt/hikvision/web/components/tomcat85linux64.2\t/usr/bin/java\t\tjava -Dcatalina.base=/opt/hikvision/web/components/tomcat85linux64.2",
          "PORT_DEPLOYMENT\t13165\t/opt/hikvision/web/components/tomcat85linux64.2/webapps/media",
        ].join("\n"),
        stderr: "",
      };
    });

    assert.equal(scripts.length, 1);
    assert.match(scripts[0].script, /target_port='6040'/);
    assert.match(scripts[0].script, /local_address/);
    assert.ok(scripts[0].overrides.timeoutMs <= 5000);
    assert.equal(result.queryStatus, "complete");
    assert.equal(result.listenerEvidence, "found");
    assert.equal(result.hosts[0].processes[0].pid, 13165);
    assert.deepEqual(
      result.hosts[0].processes[0].componentCandidates.map(item => item.value),
      ["media"],
    );
  }),
);

test("port evidence derives standalone component and service candidates structurally", () => {
  const output = [
    "PORT_SOCKET\t2468\tLISTEN 0 128 0.0.0.0:9000 0.0.0.0:* users:((orders_x86.upx,pid=2468,fd=9))",
    "PORT_PROCESS\t2468\t/opt/hikvision/web/components/billing.1\t/opt/hikvision/web/components/billing.1/bin/orders_x86.upx\t\t/opt/hikvision/web/components/billing.1/bin/orders_x86.upx",
  ].join("\n");

  const result = parsePortInspectionOutput(output, { host: "server", port: 9000 });

  assert.deepEqual(result.processes[0].componentCandidates.map(item => item.value), ["billing"]);
  assert.equal(
    result.processes[0].componentCandidates[0].path,
    "/opt/hikvision/web/components/billing.1",
  );
  assert.deepEqual(result.processes[0].serviceCandidates.map(item => item.value), ["orders"]);
});

test("port inspection script reports the precise runtime substage", () => {
  const script = buildPortInspectionScript(6040);

  assert.match(script, /inspect-port-sockets/);
  assert.match(script, /inspect-port-cwd/);
  assert.match(script, /inspect-port-cmdline/);
  assert.doesNotMatch(script, /grep -F -i --/);
});

test("port inspection does not match a different port with the same suffix", () => {
  const script = `
ss() {
  printf '%s\\n' \\
    'LISTEN 0 128 0.0.0.0:6040 0.0.0.0:* users:((demo,pid=999998,fd=9))' \\
    'LISTEN 0 128 0.0.0.0:16040 0.0.0.0:* users:((demo,pid=999999,fd=10))'
}
${buildPortInspectionScript(6040)}`;

  const output = runShell(script);

  assert.match(output, /PORT_SOCKET\t999998\t.*:6040\b/);
  assert.doesNotMatch(output, /:16040\b/);
});

test("process inspection follows an exact PID without another process snapshot", async () =>
  withFixtureAsync(async root => {
    const calls = [];
    const result = await inspectProcess(makeConfig(root), {
      environment: "192.0.2.20",
      host: "server",
      pid: 15169,
    }, async (_config, _host, script, overrides = {}) => {
      calls.push({ script, overrides });
      return {
        stdout: [
          "PROCESS_META\t15169\t1\t/opt/hikvision/web/components/media.1\t/opt/hikvision/web/components/media.1/bin/http_server\t/system.slice/hik.media.1.service\t/opt/hikvision/web/components/media.1/bin/http_server",
          "PROCESS_SOCKET\tLISTEN 0 128 0.0.0.0:6040 0.0.0.0:* users:((http_server,pid=15169,fd=9))",
          "PROCESS_FD\t7\t/opt/hikvision/web/components/media.1/logs/http/runtime-error.log\tlog",
          "PROCESS_STDIO\t1\tpipe",
          "PROCESS_UNIT\thik.media.1.service",
        ].join("\n"),
        stderr: "",
      };
    });

    assert.equal(calls.length, 1);
    assert.match(calls[0].script, /target_pid='15169'/);
    assert.match(calls[0].script, /proc_path="\/proc\/\$target_pid"/);
    assert.doesNotMatch(calls[0].script, /ps -eo/);
    assert.doesNotMatch(calls[0].script, /proc\/\[0-9\]/);
    assert.doesNotMatch(calls[0].script, /\/environ/);
    assert.ok(calls[0].overrides.timeoutMs <= 5000);
    assert.equal(result.processEvidence, "found");
    assert.equal(result.process.pid, 15169);
    assert.deepEqual(result.process.systemdUnits, ["hik.media.1.service"]);
    assert.deepEqual(result.process.logCandidates, ["/opt/hikvision/web/components/media.1/logs/http/runtime-error.log"]);
  }),
);

test("process inspection can request bounded peers from an evidenced systemd unit", () => {
  const script = buildProcessInspectionScript({
    readableRoots: ["/opt/hikvision", "/opt/opsmgr"],
  }, 15169, { includeUnitPeers: true });

  assert.match(script, /systemctl show/);
  assert.match(script, /cgroup\.procs/);
  assert.match(script, /head -n 100/);
});

test("log directory listing is bounded and metadata-only", async () =>
  withFixtureAsync(async root => {
    const logsDir = path.join(root, "components", "media.1", "logs");
    mkdirSync(logsDir, { recursive: true });
    const calls = [];
    const result = await listLogDirectory(makeConfig(root), {
      environment: "192.0.2.20",
      host: "server",
      path: realpathSync(logsDir),
      maxDepth: 2,
      limit: 50,
    }, async (_config, _host, script, overrides = {}) => {
      calls.push({ script, overrides });
      return {
        stdout: [
          "DIRECTORY_ENTRY\tdirectory\t0\t2026-08-21 10:00:00\tworker",
          "DIRECTORY_ENTRY\tfile\t128\t2026-08-21 10:01:00\tworker/runtime.log",
        ].join("\n"),
        stderr: "",
      };
    });

    assert.match(calls[0].script, /maxdepth 2/);
    assert.match(calls[0].script, /head -n 50/);
    assert.doesNotMatch(calls[0].script, /cat |grep /);
    assert.ok(calls[0].overrides.timeoutMs <= 5000);
    assert.equal(result.entries.length, 2);
    assert.equal(result.entries[1].relativePath, "worker/runtime.log");
  }),
);

test("a missing log directory is reported as not found", async () =>
  withFixtureAsync(async root => {
    const missingPath = path.join(realpathSync(root), "components", "media.1", "logs");
    const result = await listLogDirectory(makeConfig(root), {
      environment: "192.0.2.20",
      host: "server",
      path: missingPath,
    }, localRunner);

    assert.equal(result.queryStatus, "complete");
    assert.equal(result.directoryEvidence, "not-found");
    assert.deepEqual(result.entries, []);
  }),
);

test("journal search requires an exact unit and applies the widened time window", async () =>
  withFixtureAsync(async root => {
    const calls = [];
    const result = await searchJournal(makeConfig(root), {
      environment: "192.0.2.20",
      host: "server",
      unit: "hik.media.1.service",
      timeHint: "2026-08-21 11:00 到 12:00 左右",
      query: "ERROR",
      lines: 50,
    }, async (_config, _host, script, overrides = {}) => {
      calls.push({ script, overrides });
      return { stdout: "2026-08-21T11:30:00+0800 host service[1]: ERROR failed\n", stderr: "" };
    });

    assert.match(calls[0].script, /journalctl/);
    assert.match(calls[0].script, /--since '2026-08-21 10:30:00'/);
    assert.match(calls[0].script, /--until '2026-08-21 12:30:00'/);
    assert.match(calls[0].script, /grep -F/);
    assert.equal(calls[0].overrides.timeoutMs, 20000);
    assert.equal(result.timeHintStatus, "applied");
    assert.equal(result.matches.length, 1);
  }),
);

test("journal search rejects shell-like unit input before remote execution", async () =>
  withFixtureAsync(async root => {
    let called = false;
    await assert.rejects(
      searchJournal(makeConfig(root), {
        environment: "192.0.2.20",
        host: "server",
        unit: "demo.service; id",
        timeHint: "2026-08-21 11:00",
      }, async () => {
        called = true;
        return { stdout: "", stderr: "" };
      }),
      /exact systemd/,
    );
    assert.equal(called, false);
  }),
);

test("inspect service passes discovered Tomcat paths into runtime inspection", async () =>
  withFixtureAsync(async root => {
    const tomcatPath = "/opt/hikvision/web/components/tomcat85linux64.2";
    const deploymentPath = `${tomcatPath}/webapps/logservice`;
    const calls = [];
    const runner = async (_config, _host, script, overrides = {}) => {
      calls.push({ script, overrides });
      if (script.includes("inspect-component-files")) {
        return { stdout: `DEPLOYMENT\t${tomcatPath}\t${deploymentPath}\n`, stderr: "" };
      }
      if (script.includes("inspect-processes")) {
        return {
          stdout: `PROCESS\t13165\t1\ttomcat-path\t${tomcatPath}\t/java\t\tjava -Dcatalina.base=${tomcatPath}\n`,
          stderr: "",
        };
      }
      return { stdout: "", stderr: "" };
    };

    const result = await inspectService(makeConfig(root), {
      environment: "192.0.2.20",
      component: "logservice",
      service: "log",
    }, runner);

    const runtimeCall = calls.find(call => call.script.includes("inspect-processes"));
    assert.ok(runtimeCall);
    assert.match(runtimeCall.script, new RegExp(tomcatPath.replaceAll("/", "\\/")));
    assert.equal(result.services[0].runtimeInstances[0].matchConfidence, "strong");
  }),
);

test("inspect service runs bounded layout and runtime stages separately", async () =>
  withFixtureAsync(async root => {
    const secondRoot = path.join(root, "legacy-root");
    mkdirSync(secondRoot, { recursive: true });
    const calls = [];
    const runner = async (_config, _host, script, overrides = {}) => {
      calls.push({ script, overrides });
      if (script.includes("inspect-processes")) {
        return {
          stdout: "PROCESS\t321\t1\tservice-executable\t/opt/app\t/opt/app/orders\t\t/opt/app/orders\n",
          stderr: "",
        };
      }
      if (script.includes("inspect-sockets")) return { stdout: "", stderr: "" };
      return { stdout: "", stderr: "" };
    };

    const result = await inspectService(makeConfig(root, [secondRoot]), {
      environment: "192.0.2.20",
      component: "acme",
      service: "orders",
    }, runner);

    assert.equal(calls.filter(call => call.script.includes("inspect-component-files")).length, 1);
    assert.equal(calls.filter(call => call.script.includes("inspect-processes")).length, 1);
    assert.equal(calls.filter(call => call.script.includes("inspect-processes") && call.script.includes("legacy-root")).length, 0);
    assert.equal(calls.some(call => call.script.includes("inspect-component-files") && call.script.includes("inspect-processes")), false);
    assert.ok(calls.every(call => call.overrides.timeoutMs <= 10000));
    assert.equal(result.runtimeEvidence, "found");
  }),
);

test("known component inspection avoids broad file scans and unbounded systemd", () =>
  withFixture(root => {
    const script = buildInspectionScript(
      makeHost(root),
      makeRule(),
      root,
      "screening",
      "opslog",
      20,
    );

    assert.doesNotMatch(script, /find "\$resolved_path"/);
    assert.doesNotMatch(script, /find "\$component_path"/);
    assert.doesNotMatch(script, /find "\$tomcat_path"/);
    assert.doesNotMatch(script, /^\s*systemctl list-units/m);
    assert.match(script, /timeout 2s systemctl list-units/);
  }),
);

test("remote stage diagnostics survive output chunk boundaries", () => {
  const state = { tail: "", lastStage: "" };
  extractRemoteStage(state, Buffer.from("noise\n__RL_STA"));
  extractRemoteStage(state, Buffer.from("GE__\tinspect-processes\nmore\n"));
  assert.equal(state.lastStage, "inspect-processes");
  extractRemoteStage(state, Buffer.from("__RL_STAGE__\tinspect-process-cgroup\n"));
  assert.equal(state.lastStage, "inspect-process-cgroup");
});

test("inspect timeout remains unknown instead of reporting a stopped service", async () =>
  withFixtureAsync(async root => {
    const result = await inspectService(makeConfig(root), {
      environment: "192.0.2.20",
      component: "screening",
      service: "opslog",
    }, async (_config, _host, script, overrides = {}) => {
      if (!script.includes("inspect-processes")) return { stdout: "", stderr: "" };
      throw new Error(`remote command timed out after ${overrides.timeoutMs} ms (phase=execute, stage=inspect-processes)`);
    });

    assert.equal(result.queryStatus, "timed-out");
    assert.equal(result.deploymentEvidence, "unknown");
    assert.equal(result.runtimeEvidence, "unknown");
    assert.equal(result.warnings[0].operation, "inspect_service");
    assert.equal(result.warnings[0].inspectionPart, "processes");
    assert.equal(result.warnings[0].phase, "execute");
    assert.equal(result.warnings[0].stage, "inspect-processes");
    assert.equal(result.warnings[0].timedOut, true);
  }),
);

test("component log discovery timeout does not ask the user to choose a service", async () =>
  withFixtureAsync(async root => {
    const result = await searchLogs(makeConfig(root), {
      environment: "192.0.2.20",
      scope: "service",
      component: "screening",
      query: "ERROR",
    }, async () => {
      throw new Error("remote command timed out after 30000 ms");
    });

    assert.equal(result.queryStatus, "timed-out");
    assert.equal(result.requiresServiceSelection, false);
    assert.deepEqual(result.serviceCandidates, []);
    assert.equal(result.warnings[0].operation, "discover_component_services");
  }),
);

test("the MCP server starts when its entry path traverses a symbolic link", {
  skip: process.platform === "win32",
}, () => withFixture(root => {
  const linkedEntry = path.join(root, "runtime-lens-server.mjs");
  symlinkSync(fileURLToPath(new URL("./server.mjs", import.meta.url)), linkedEntry);
  const initialize = JSON.stringify({
    jsonrpc: "2.0",
    id: 1,
    method: "initialize",
    params: {
      protocolVersion: "2024-11-05",
      capabilities: {},
      clientInfo: { name: "runtime-lens-test", version: "1" },
    },
  });
  const listTools = JSON.stringify({ jsonrpc: "2.0", id: 2, method: "tools/list", params: {} });

  const output = execFileSync(process.execPath, [linkedEntry], {
    input: `${initialize}\n${listTools}\n`,
    encoding: "utf8",
  });

  assert.match(output, /"name":"runtime-lens"/);
  assert.match(output, /"version":"0\.11\.0"/);
  assert.match(output, /"name":"inspect_port"/);
  assert.match(output, /"name":"inspect_process"/);
  assert.match(output, /"name":"list_log_directory"/);
  assert.match(output, /"name":"search_journal"/);
}));
