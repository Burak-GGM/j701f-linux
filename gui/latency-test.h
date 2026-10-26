// Offscreen PTY -> normal terminal paint -> compositor measurement.
// No framebuffer, input device, user login shell or shell history is used.
#pragma once
#include <QApplication>
#include <QElapsedTimer>
#include <QEvent>
#include <QPointer>
#include <QTimer>
#include <QWidget>
#include <qtermwidget.h>
#include <algorithm>
#include <functional>
#include <vector>

class TerminalLatencyTest : public QObject {
    QTermWidget *terminal;
    const bool *presenting;
    QElapsedTimer clock;
    QTimer deadline;
    QString token, received;
    qint64 sent = -1, read = -1, painted = -1;
    unsigned sample = 0;
    bool active = false, complete = false;
    std::vector<qint64> totals;
    void fail(const char *reason) {
        if (complete) return;
        complete = true; deadline.stop();
        qCritical("J701F_TERMINAL_LATENCY_FAILED %s", reason);
        QApplication::exit(2);
    }
    void send() {
        if (complete) return;
        ++sample;
        token = QString("J701F_LATENCY_%1").arg(sample, 4, 10, QLatin1Char('0'));
        received.clear(); read = painted = -1;
        sent = clock.nsecsElapsed(); active = true;
        deadline.start(1200);
        terminal->sendText(token + "\n");
    }
public:
    std::function<void()> onComplete;
    TerminalLatencyTest(QTermWidget *widget, const bool *inRender, QObject *parent)
        : QObject(parent), terminal(widget), presenting(inRender) {
        clock.start(); deadline.setSingleShot(true);
        connect(&deadline, &QTimer::timeout, this, [this] { fail("PTY/paint/presentation timeout"); });
        connect(terminal, &QTermWidget::receivedData, this, [this](const QString &data) {
            if (!active || complete) return;
            received += data;
            if (read < 0 && received.contains(token)) read = clock.nsecsElapsed();
        });
        qApp->installEventFilter(this);
    }
    ~TerminalLatencyTest() override { qApp->removeEventFilter(this); }
    void start() { send(); }
    bool eventFilter(QObject *object, QEvent *event) override {
        auto *widget = qobject_cast<QWidget *>(object);
        if (active && !*presenting && read >= 0 && painted < 0 && event->type() == QEvent::Paint &&
            widget && terminal->isAncestorOf(widget) &&
            QString::fromLatin1(widget->metaObject()->className()).endsWith("TerminalDisplay"))
            painted = clock.nsecsElapsed();
        return false;
    }
    void presented(qint64 renderNs) {
        if (!active || complete || painted < 0) return;
        qint64 now = clock.nsecsElapsed();
        deadline.stop(); active = false;
        totals.push_back(now - sent);
        qInfo("J701F_TERMINAL_LATENCY sample=%u pty_us=%lld paint_us=%lld frame_us=%lld render_us=%lld total_us=%lld",
              sample, (read - sent) / 1000, (painted - read) / 1000,
              (now - painted) / 1000, renderNs / 1000, (now - sent) / 1000);
        if (sample == 16) {
            std::sort(totals.begin(), totals.end()); complete = true;
            qInfo("J701F_TERMINAL_LATENCY_PASS samples=%zu median_us=%lld p95_us=%lld max_us=%lld",
                  totals.size(), totals[totals.size() / 2] / 1000,
                  totals[(totals.size() * 95 + 99) / 100 - 1] / 1000, totals.back() / 1000);
            if (onComplete) onComplete(); else QApplication::quit();
        } else QTimer::singleShot(120, this, [this] { send(); });
    }
};
