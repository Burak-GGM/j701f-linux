// First Qt Widgets GUI on the measured J701F framebuffer; no GPU or window server.
#include <QApplication>
#include <QDir>
#include <QElapsedTimer>
#include <QFile>
#include <QFont>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QKeyEvent>
#include <QLabel>
#include <QListWidget>
#include <QMouseEvent>
#include <QPaintEvent>
#include <QPointer>
#include <QPushButton>
#include <QScreen>
#include <QSocketNotifier>
#include <QStackedWidget>
#include <QTimer>
#include <QVBoxLayout>
#include <qtermwidget.h>
#include <linux/fb.h>
#include <linux/input.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#include <array>
#include <algorithm>
#include <vector>
#include <cerrno>
#include <cstring>
#include <memory>
#include <stdexcept>
#include "latency-test.h"

// Observe normal Qt repaints; rendering our output must not schedule itself again.
class ScreenChanges : public QObject {
    QWidget *root;
    QRegion damage;
public:
    bool presenting = false;
    std::function<void()> schedule;
    explicit ScreenChanges(QWidget *widget) : root(widget), damage(widget->rect()) {}
    QRegion takeDamage() {
        QRegion result = damage & root->rect();
        damage = QRegion();
        return result;
    }
    bool eventFilter(QObject *object, QEvent *event) override {
        auto *widget = qobject_cast<QWidget *>(object);
        if (presenting || !widget || (widget != root && !root->isAncestorOf(widget))) return false;
        if (event->type() == QEvent::Paint && widget->isVisible()) {
            damage += static_cast<QPaintEvent *>(event)->region().translated(widget->mapTo(root, QPoint()));
        } else if (event->type() == QEvent::Move || event->type() == QEvent::Resize ||
                   event->type() == QEvent::Show || event->type() == QEvent::Hide) {
            // Geometry/visibility changes must also erase the widget's previous footprint.
            damage = root->rect();
        }
        if (!damage.isEmpty() && schedule) schedule();
        return false;
    }
};

static QString readFile(const QString &path) {
    QFile file(path);
    return file.open(QIODevice::ReadOnly) ? QString::fromUtf8(file.readAll()).trimmed() : QStringLiteral("unavailable");
}

class Framebuffer {
    int fd = -1;
    fb_var_screeninfo var{};
    fb_fix_screeninfo fix{};
    unsigned char *map = nullptr;
    QByteArray previous;
    QImage lastFrame{720, 1280, QImage::Format_RGB32};
    bool firstFrame = true;
    bool swapRB = false;
    void validate() {
        if (var.xres != 720 || var.yres != 1280 || var.bits_per_pixel != 32 ||
            fix.type != FB_TYPE_PACKED_PIXELS || fix.line_length != 2880 ||
            fix.smem_len < 720 * 1280 * 4 || fix.smem_len > 128 * 1024 * 1024 ||
            var.red.offset != 16 || var.red.length != 8 || var.red.msb_right ||
            var.green.offset != 8 || var.green.length != 8 || var.green.msb_right ||
            var.blue.offset != 0 || var.blue.length != 8 || var.blue.msb_right ||
            !((fix.visual == FB_VISUAL_TRUECOLOR && var.transp.offset == 24 && var.transp.length == 8 && !var.transp.msb_right) ||
              (fix.visual == 0 && var.transp.length == 0)) ||
            (quint64(var.xoffset) + var.xres) * 4 > fix.line_length ||
            (quint64(var.yoffset) + var.yres - 1) * fix.line_length + (quint64(var.xoffset) + var.xres) * 4 > fix.smem_len)
            throw std::runtime_error("Framebuffer does not match the measured J701F layout");
    }
public:
    Framebuffer() {
        fd = open("/dev/fb0", O_RDWR | O_CLOEXEC);
        if (fd < 0 || ioctl(fd, FBIOGET_VSCREENINFO, &var) < 0 || ioctl(fd, FBIOGET_FSCREENINFO, &fix) < 0)
            throw std::runtime_error("Cannot read framebuffer");
        validate();
        if (ioctl(fd, FBIOBLANK, FB_BLANK_UNBLANK) < 0) throw std::runtime_error("Cannot unblank framebuffer");
        var.activate = FB_ACTIVATE_NOW | FB_ACTIVATE_FORCE;
        if (ioctl(fd, FBIOPUT_VSCREENINFO, &var) < 0 || ioctl(fd, FBIOGET_VSCREENINFO, &var) < 0 ||
            ioctl(fd, FBIOGET_FSCREENINFO, &fix) < 0) throw std::runtime_error("Cannot activate framebuffer");
        validate();
        swapRB = fix.visual == FB_VISUAL_TRUECOLOR && var.transp.length == 8;
        map = static_cast<unsigned char *>(mmap(nullptr, fix.smem_len, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0));
        if (map == MAP_FAILED) { map = nullptr; throw std::runtime_error("Cannot map framebuffer"); }
        previous = QByteArray(reinterpret_cast<const char *>(map), fix.smem_len);
        var.activate = FB_ACTIVATE_NOW;
        qInfo("J701F_FRAMEBUFFER_READY %ux%u swap_rb=%d", var.xres, var.yres, swapRB);
    }
    ~Framebuffer() {
        if (map) {
            std::memcpy(map, previous.constData(), fix.smem_len);
            ioctl(fd, FBIOPAN_DISPLAY, &var);
            munmap(map, fix.smem_len);
        }
        if (fd >= 0) close(fd);
    }
    void present(const QImage &image) {
        bool changed = false;
        std::array<quint32, 720> packed;
        for (unsigned y = 0; y < var.yres; ++y) {
            const auto *source = reinterpret_cast<const quint32 *>(image.constScanLine(y));
            auto *last = lastFrame.scanLine(y);
            if (!firstFrame && std::memcmp(source, last, 720 * 4) == 0) continue;
            std::memcpy(last, source, 720 * 4);
            auto *target = reinterpret_cast<quint32 *>(map + (y + var.yoffset) * fix.line_length + var.xoffset * 4);
            for (unsigned x = 0; x < var.xres; ++x) {
                quint32 p = source[x] | 0xff000000;
                if (swapRB) p = (p & 0xff00ff00) | ((p & 0xff0000) >> 16) | ((p & 0xff) << 16);
                packed[x] = p;
            }
            std::memcpy(target, packed.data(), 720 * 4);
            changed = true;
        }
        firstFrame = false;
        if (changed && ioctl(fd, FBIOPAN_DISPLAY, &var) < 0) qWarning("Framebuffer pan failed: %s", strerror(errno));
    }
};

class Touch {
    struct Slot { int x = 0, y = 0; bool active = false, haveX = false, haveY = false; };
    std::array<Slot, 32> contacts{};
    int fd = -1, selected = 0;
    input_absinfo ax{}, ay{};
    QWidget *root;
    QPointer<QWidget> pressed;
    std::unique_ptr<QSocketNotifier> notifier;
    QPoint point;
    bool dropped = false;
    void mouse(QEvent::Type type, Qt::MouseButton button, Qt::MouseButtons buttons) {
        if (!pressed) return;
        const QPoint local = pressed->mapFrom(root, point);
        const QPoint global = root->mapToGlobal(point);
        QMouseEvent event(type, QPointF(local), QPointF(point), QPointF(global), button, buttons, Qt::NoModifier);
        QApplication::sendEvent(pressed, &event);
    }
    void release() {
        mouse(QEvent::MouseButtonRelease, Qt::LeftButton, Qt::NoButton);
        pressed.clear();
    }
    void consume() {
        input_event events[64];
        ssize_t bytes;
        while ((bytes = read(fd, events, sizeof(events))) > 0) {
            for (int i = 0; i < bytes / ssize_t(sizeof(input_event)); ++i) {
                const auto &e = events[i];
                if (e.type == EV_SYN && e.code == SYN_DROPPED) {
                    point = QPoint(-100, -100); release(); contacts = {}; dropped = true; continue;
                }
                if (dropped) { if (e.type == EV_SYN && e.code == SYN_REPORT) dropped = false; continue; }
                if (e.type == EV_ABS && e.code == ABS_MT_SLOT) { selected = e.value; continue; }
                if (e.type == EV_ABS && selected >= 0 && selected < int(contacts.size())) {
                    auto &s = contacts[selected];
                    if (e.code == ABS_MT_TRACKING_ID) { s.active = e.value >= 0;  }
                    if (e.code == ABS_MT_POSITION_X) { s.x = e.value; s.haveX = true; }
                    if (e.code == ABS_MT_POSITION_Y) { s.y = e.value; s.haveY = true; }
                }
                if (e.type == EV_SYN && e.code == SYN_REPORT) {
                    auto it = std::find_if(contacts.begin(), contacts.end(), [](const Slot &s) { return s.active && s.haveX && s.haveY; });
                    if (it == contacts.end()) { release(); continue; }
                    point = QPoint(qBound(0, int(qint64(it->x - ax.minimum) * (root->width() - 1) / (ax.maximum - ax.minimum)), root->width() - 1),
                                   qBound(0, int(qint64(it->y - ay.minimum) * (root->height() - 1) / (ay.maximum - ay.minimum)), root->height() - 1));
                    if (!pressed) {
                        pressed = root->childAt(point);
                        if (!pressed) pressed = root;
                        mouse(QEvent::MouseButtonPress, Qt::LeftButton, Qt::LeftButton);
                    } else mouse(QEvent::MouseMove, Qt::NoButton, Qt::LeftButton);
                }
            }
        }
    }
public:
    explicit Touch(QWidget *widget) : root(widget) {
        for (const QString &name : QDir("/dev/input").entryList({"event*"}, QDir::System)) {
            int candidate = open(qPrintable("/dev/input/" + name), O_RDONLY | O_NONBLOCK | O_CLOEXEC);
            input_absinfo slot{};
            if (candidate >= 0 && ioctl(candidate, EVIOCGABS(ABS_MT_POSITION_X), &ax) == 0 &&
                ioctl(candidate, EVIOCGABS(ABS_MT_POSITION_Y), &ay) == 0 &&
                ioctl(candidate, EVIOCGABS(ABS_MT_SLOT), &slot) == 0 &&
                ax.maximum > ax.minimum && ay.maximum > ay.minimum && slot.minimum == 0 && slot.maximum < 32) {
                if (ioctl(candidate, EVIOCGRAB, 1) < 0) { close(candidate); continue; }
                fd = candidate;
                qInfo("J701F_TOUCH_READY %s", qPrintable(name)); break;
            }
            if (candidate >= 0) close(candidate);
        }
        if (fd < 0) throw std::runtime_error("No supported touchscreen could be grabbed");
        notifier = std::make_unique<QSocketNotifier>(fd, QSocketNotifier::Read);
        QObject::connect(notifier.get(), &QSocketNotifier::activated, root, [this] { consume(); });
    }
    ~Touch() { if (fd >= 0) { ioctl(fd, EVIOCGRAB, 0); close(fd); } }
};

int main(int argc, char **argv) {
    qputenv("QT_QPA_PLATFORM", "offscreen");
    QApplication app(argc, argv);
    const bool latencyTest = app.arguments().contains("--latency-test");
    const bool checkRender = app.arguments().contains("--check-render");
    if ((latencyTest || checkRender) && !app.arguments().contains("--no-fb")) {
        qCritical("Latency test requires --no-fb; it never uses the screen or touchscreen"); return 1;
    }
    if (checkRender && !latencyTest) { qCritical("--check-render requires --latency-test"); return 1; }
    QApplication::setStyle("Fusion");
    QFont font("DejaVu Sans"); font.setPixelSize(24); app.setFont(font);
    app.setStyleSheet("QWidget { background: #111b22; color: #eaf2f5; } QPushButton { background: #263740; border: 1px solid #405661; border-radius: 10px; padding: 12px; min-height: 36px; } QPushButton:pressed, QPushButton:checked { background: #238957; } QListWidget { border: 1px solid #405661; } QListWidget::item { padding: 16px; } QListWidget::item:selected { background: #238957; }");
    QWidget root;
    root.resize(720, 1280);
    auto *layout = new QVBoxLayout(&root); layout->setContentsMargins(18, 18, 18, 18); layout->setSpacing(12);
    auto *heading = new QLabel("BURAK LINUX");
    QFont title = font; title.setPixelSize(36); title.setBold(true); heading->setFont(title); layout->addWidget(heading);
    auto *subtitle = new QLabel("First graphical session  •  Qt Widgets"); layout->addWidget(subtitle);
    auto *navigation = new QHBoxLayout; layout->addLayout(navigation);
    auto *pages = new QStackedWidget; layout->addWidget(pages, 1);
    auto button = [](const QString &text) { auto *b = new QPushButton(text); b->setFocusPolicy(Qt::NoFocus); return b; };
    auto *terminalPage = new QWidget; auto *terminalLayout = new QVBoxLayout(terminalPage); terminalLayout->setContentsMargins(0, 0, 0, 0);
    auto *terminal = new QTermWidget(0); QFont mono("DejaVu Sans Mono"); mono.setPixelSize(20); terminal->setTerminalFont(mono);
    if (latencyTest) {
        terminal->setShellProgram("/bin/sh");
        terminal->setArgs({"-c", "stty -echo; printf '\\033[?25l'; while IFS= read -r line; do printf '\\033[H%s\\n' \"$line\"; done"});
        terminal->setBlinkingCursor(false);
    } else {
        terminal->setShellProgram("/usr/bin/sudo"); terminal->setArgs({"-n", "-u", "burak-alpine", "-H", "/bin/sh", "-l"});
    }
    terminal->setWorkingDirectory("/home/burak-alpine"); terminal->setHistorySize(1500);
    terminal->setScrollBarPosition(QTermWidget::ScrollBarRight); terminalLayout->addWidget(terminal, 1);
    auto *keyboard = new QWidget; auto *keys = new QGridLayout(keyboard); keys->setContentsMargins(0, 0, 0, 0); keys->setSpacing(5);
    struct Key { QPushButton *button; QString normal, shifted; };
    std::vector<Key> letters;
    bool shift = false, control = false;
    const QStringList rows = {"1234567890", "qwertyuiop", "asdfghjkl", "zxcvbnm,."};
    const QString shiftedDigits = "!@#$%^&*()";
    for (int row = 0; row < rows.size(); ++row) for (int column = 0; column < rows[row].size(); ++column) {
        QString normal = rows[row].mid(column, 1);
        QString shifted = row == 0 ? shiftedDigits.mid(column, 1) : normal.toUpper();
        if (normal == ",") shifted = "<";
        if (normal == ".") shifted = ">";
        auto *b = button(normal); b->setFixedHeight(65); keys->addWidget(b, row, column);
        letters.push_back({b, normal, shifted});
        QObject::connect(b, &QPushButton::clicked, &root, [&, normal, shifted] {
            QString text = shift ? shifted : normal;
            if (control && normal[0].isLetter()) text = QString(QChar(normal[0].toLower().unicode() - 'a' + 1));
            terminal->sendText(text); terminal->setFocus();
        });
    }
    auto *shiftButton = button("Shift"); shiftButton->setCheckable(true); keys->addWidget(shiftButton, 4, 0, 1, 2);
    auto *ctrlButton = button("Ctrl"); ctrlButton->setCheckable(true); keys->addWidget(ctrlButton, 4, 2, 1, 2);
    QObject::connect(shiftButton, &QPushButton::toggled, &root, [&](bool value) { shift = value; for (auto &key : letters) key.button->setText(shift ? key.shifted : key.normal); });
    QObject::connect(ctrlButton, &QPushButton::toggled, &root, [&](bool value) { control = value; });
    auto special = [&](const QString &label, const QString &text, int row, int column, int span = 1) {
        auto *b = button(label); keys->addWidget(b, row, column, 1, span);
        QObject::connect(b, &QPushButton::clicked, &root, [=] { terminal->sendText(text); terminal->setFocus(); });
    };
    special("Space", " ", 4, 4, 3); special("Del", "\x7f", 4, 7); special("Enter", "\r", 4, 8, 2);
    special("Esc", "\x1b", 5, 0, 2); special("Tab", "\t", 5, 2, 2);
    special("/", "/", 5, 4); special("-", "-", 5, 5);
    special("←", "\x1b[D", 5, 6); special("↓", "\x1b[B", 5, 7); special("↑", "\x1b[A", 5, 8); special("→", "\x1b[C", 5, 9);
    terminalLayout->addWidget(keyboard); pages->addWidget(terminalPage);
    auto *filesPage = new QWidget; auto *fileLayout = new QVBoxLayout(filesPage); auto *pathLabel = new QLabel; pathLabel->setWordWrap(true);
    auto *up = button("Parent directory"); auto *files = new QListWidget; fileLayout->addWidget(pathLabel); fileLayout->addWidget(up); fileLayout->addWidget(files, 1);
    QString directory = "/home/burak-alpine";
    auto refreshFiles = [&] {
        pathLabel->setText(directory); files->clear();
        const auto entries = QDir(directory).entryInfoList(QDir::AllEntries | QDir::NoDotAndDotDot, QDir::DirsFirst | QDir::Name);
        for (const auto &entry : entries) {
            auto *item = new QListWidgetItem((entry.isDir() ? "▸  " : "    ") + entry.fileName(), files);
            item->setData(Qt::UserRole, entry.absoluteFilePath()); item->setData(Qt::UserRole + 1, entry.isDir());
        }
        if (files->count() == 0) { auto *empty = new QListWidgetItem("This directory is empty", files); empty->setFlags(Qt::NoItemFlags); }
    };
    QObject::connect(up, &QPushButton::clicked, &root, [&] { QDir dir(directory); if (dir.cdUp()) directory = dir.absolutePath(); refreshFiles(); });
    QObject::connect(files, &QListWidget::itemClicked, &root, [&](QListWidgetItem *item) { if (item->data(Qt::UserRole + 1).toBool()) { directory = item->data(Qt::UserRole).toString(); refreshFiles(); } });
    refreshFiles(); pages->addWidget(filesPage);
    auto *status = new QLabel; status->setAlignment(Qt::AlignTop); status->setWordWrap(true); status->setMargin(16); pages->addWidget(status);
    auto refreshStatus = [&] {
        QString online = readFile("/sys/devices/system/cpu/online");
        QString battery = readFile("/sys/class/power_supply/battery/capacity");
        QString uptime = readFile("/proc/uptime").section(' ', 0, 0);
        status->setText("SYSTEM STATUS\n\nAlpine " + readFile("/etc/alpine-release") + "\n\nCPU cores online: " + online + "\n\nBattery: " + battery + "%\n\nUptime: " + uptime + " seconds\n\nDisplay: 720 × 1280\nRenderer: Qt software raster\n\nTerminal user: burak-alpine\n\nGPU acceleration is a later milestone.");
    };
    refreshStatus();
    for (int i = 0; i < 3; ++i) {
        auto *b = button(QStringList{"Terminal", "Files", "Status"}[i]); navigation->addWidget(b);
        QObject::connect(b, &QPushButton::clicked, &root, [&, i] { pages->setCurrentIndex(i); if (i == 0) terminal->setFocus(); if (i == 2) refreshStatus(); });
    }
    auto *exitButton = button("Exit GUI"); navigation->addWidget(exitButton);
    QObject::connect(exitButton, &QPushButton::clicked, &app, &QApplication::quit);
    QObject::connect(terminal, &QTermWidget::finished, &app, &QApplication::quit);
    auto *footer = new QLabel("Touch to explore  •  Exit GUI returns to the original terminal"); footer->setWordWrap(true); footer->setStyleSheet("color: #9eb5c0; font-size: 18px;"); layout->addWidget(footer);
    root.show(); root.activateWindow(); terminal->startShellProgram(); terminal->setFocus();
    std::unique_ptr<Framebuffer> fb;
    std::unique_ptr<Touch> touch;
    const bool noFramebuffer = app.arguments().contains("--no-fb");
    try { if (!noFramebuffer) { fb = std::make_unique<Framebuffer>(); touch = std::make_unique<Touch>(&root); } }
    catch (const std::exception &error) { qCritical("GUI initialization: %s", error.what()); return 1; }
    QImage image(720, 1280, QImage::Format_RGB32);
    ScreenChanges changes(&root);
    app.installEventFilter(&changes);
    std::unique_ptr<TerminalLatencyTest> latency;
    if (latencyTest) latency = std::make_unique<TerminalLatencyTest>(terminal, &changes.presenting, &root);
    QElapsedTimer elapsed;
    elapsed.start();
    quint64 frames = 0, renderingMs = 0, worstMs = 0;
    quint64 verifiedFrames = 0;
    if (checkRender) latency->onComplete = [&] {
        // Exercise real page/keyboard slots after the PTY samples, still offscreen.
        std::vector<std::function<void()>> steps = {
            [&] { pages->setCurrentIndex(1); },
            [&] { pages->setCurrentIndex(2); refreshStatus(); },
            [&] { pages->setCurrentIndex(0); terminal->setFocus(); },
            [&] { shiftButton->click(); },
            [&] { ctrlButton->click(); },
            [&] { ctrlButton->click(); shiftButton->click(); letters.front().button->click(); terminal->sendText("\r"); },
            [&] { pages->setCurrentIndex(1); up->click(); },
            [&] { pages->setCurrentIndex(0); terminal->setFocus(); }
        };
        for (size_t i = 0; i < steps.size(); ++i)
            QTimer::singleShot(int(i + 1) * 400, &root, [step=steps[i], i] {
                step(); qInfo("J701F_RENDER_CHECK_STAGE %zu", i + 1);
            });
        QTimer::singleShot(3800, &root, [&] {
            if (verifiedFrames < 24) { qCritical("Insufficient render validation frames"); app.exit(2); return; }
            qInfo("J701F_RENDER_CHECK_PASS frames=%llu interactions=8", static_cast<unsigned long long>(verifiedFrames));
            app.quit();
        });
    };
    QTimer render;
    const bool pollRender = app.arguments().contains("--poll-render");
    render.setSingleShot(!pollRender);
    if (!pollRender) changes.schedule = [&] { if (!render.isActive()) render.start(0); };
    QObject::connect(&render, &QTimer::timeout, &root, [&] {
        QRegion damage = changes.takeDamage();
        if (damage.isEmpty()) return;
        if (app.arguments().contains("--full-render")) damage = root.rect();
        changes.presenting = true;
        QElapsedTimer work; work.start();
        root.render(&image, damage.boundingRect().topLeft(), damage);
        changes.presenting = false;
        if (fb) fb->present(image);
        if (latency) latency->presented(work.nsecsElapsed());
        const quint64 ms = work.elapsed();
        ++frames; renderingMs += ms; worstMs = std::max(worstMs, ms);
        if (checkRender) {
            QImage reference(image.size(), image.format());
            changes.presenting = true;
            root.render(&reference);
            changes.presenting = false;
            if (image != reference) {
                qCritical("J701F_RENDER_CHECK_FAILED frame=%llu", static_cast<unsigned long long>(frames));
                app.exit(2);
            } else ++verifiedFrames;
        }
    });
    render.start(pollRender ? 30 : 0);
    QTimer::singleShot(700, &root, [&] {
        if (latency) { latency->start(); return; }
        terminal->sendText("printf 'Qt graphical terminal ready\\n'; id\r");
        qInfo("J701F_QT_GUI_READY");
    });
    QTimer::singleShot(2000, &root, [&] {
        if (latencyTest) return;
        changes.presenting = true;
        root.render(&image);
        changes.presenting = false;
        if (app.arguments().contains("--screenshot")) image.save("/tmp/j701f-gui.png");
    });
    int timeout = 180;
    const int timeoutIndex = app.arguments().indexOf("--seconds");
    if (timeoutIndex >= 0 && timeoutIndex + 1 < app.arguments().size()) timeout = app.arguments()[timeoutIndex + 1].toInt();
    if (timeout > 0) QTimer::singleShot(timeout * 1000, &app, &QApplication::quit);
    const int result = app.exec();
    qInfo("J701F_GUI_PERF frames=%llu elapsed_ms=%lld render_total_ms=%llu render_worst_ms=%llu",
          static_cast<unsigned long long>(frames), static_cast<long long>(elapsed.elapsed()),
          static_cast<unsigned long long>(renderingMs), static_cast<unsigned long long>(worstMs));
    qInfo("J701F_QT_GUI_EXIT");
    return result;
}
