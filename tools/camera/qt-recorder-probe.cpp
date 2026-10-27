// Written by Claude 2026-10-27. Mirrors Plasma Camera 2.1.1's recording path:
// QImage frames through a QVideoFrameInput into a QMediaRecorder (MP4, H.264,
// MP3), timestamps set per frame, frame rate 0. "yuv" sends planar YUV 4:2:0
// frames instead, "audio" adds the default microphone.
//
//   qt-recorder-probe OUT.mp4 FRAMES WIDTH HEIGHT [audio] [yuv]
//
// Built on the computer against the release root (build/release/work/rootfs)
// plus the headers of Alpine's qt6-qtmultimedia-dev of the same version:
//   clang++ --target=aarch64-alpine-linux-musl --sysroot=ROOT -fuse-ld=lld -std=c++17 \
//     -I ROOT/usr/include/qt6{,/QtCore,/QtGui} -I DEV/usr/include/qt6{,/QtMultimedia} \
//     qt-recorder-probe.cpp ROOT/usr/lib/libQt6Multimedia.so.6 -L ROOT/usr/lib -lQt6Gui -lQt6Core
// and run with qemu-aarch64 through ROOT/lib/ld-musl-aarch64.so.1 --library-path.
#include <QAudioDevice>
#include <QAudioInput>
#include <QCoreApplication>
#include <QGuiApplication>
#include <QImage>
#include <QMediaCaptureSession>
#include <QMediaDevices>
#include <QMediaFormat>
#include <QMediaRecorder>
#include <QTimer>
#include <QUrl>
#include <QVideoFrame>
#include <QVideoFrameInput>
#include <cstdio>
#include <cstring>
#include <QVideoFrameFormat>

int main(int argc, char **argv)
{
    QGuiApplication app(argc, argv);
    const QString out = QString::fromLocal8Bit(argv[1]);
    const int frames = atoi(argv[2]), w = atoi(argv[3]), h = atoi(argv[4]);
    const bool audio = argc > 5 && QByteArray(argv[5]) == "audio";
    const bool yuv = argc > 5 && QByteArray(argv[argc - 1]) == "yuv";

    QMediaCaptureSession session;
    QVideoFrameInput input;
    QMediaRecorder recorder;
    QAudioInput *mic = nullptr;
    session.setVideoFrameInput(&input);
    if (audio) {
        mic = new QAudioInput(QMediaDevices::defaultAudioInput(), &app);
        session.setAudioInput(mic);
        printf("audio input: %s\n", qPrintable(QMediaDevices::defaultAudioInput().description()));
    }
    session.setRecorder(&recorder);
    QMediaFormat fmt;
    fmt.setFileFormat(QMediaFormat::FileFormat::MPEG4);
    fmt.setAudioCodec(QMediaFormat::AudioCodec::MP3);
    fmt.setVideoCodec(QMediaFormat::VideoCodec::H264);
    recorder.setMediaFormat(fmt);
    recorder.setQuality(QMediaRecorder::NormalQuality);
    // PROBE_TARGET=1 with PROBE_TARGET_W/H records at that size, like Plasma
    // Camera's resolution presets; otherwise at the frames' own size ("Auto").
    if (qEnvironmentVariableIsSet("PROBE_TARGET"))
        recorder.setVideoResolution(QSize(qEnvironmentVariableIntValue("PROBE_TARGET_W"), qEnvironmentVariableIntValue("PROBE_TARGET_H")));
    else
        recorder.setVideoResolution(QSize());
    recorder.setVideoFrameRate(0);
    recorder.setOutputLocation(QUrl::fromLocalFile(out));

    int n = 0, sent = 0;
    QTimer timer;
    timer.setInterval(33);
    QObject::connect(&timer, &QTimer::timeout, [&]() {
        if (n >= frames) { timer.stop(); recorder.stop(); return; }
        QVideoFrame frame;
        if (yuv) {
            // What a camera app could send instead of a QImage: planar YUV 4:2:0.
            frame = QVideoFrame(QVideoFrameFormat(QSize(w, h), QVideoFrameFormat::Format_YUV420P));
            frame.map(QVideoFrame::WriteOnly);
            for (int p = 0; p < frame.planeCount(); ++p)
                memset(frame.bits(p), p ? 128 : (n * 7) & 255, frame.mappedBytes(p));
            frame.unmap();
        } else {
            QImage img(w, h, QImage::Format_RGB32);
            img.fill(QColor::fromHsv((n * 6) % 360, 200, 200));
            frame = QVideoFrame(img);
        }
        const qint64 us = 1000000 / 30;
        frame.setStartTime(n * us);
        frame.setEndTime((n + 1) * us - 1);
        sent += input.sendVideoFrame(frame);
        ++n;
    });
    QObject::connect(&recorder, &QMediaRecorder::errorOccurred, [](QMediaRecorder::Error e, const QString &s) {
        printf("ERROR %d %s\n", int(e), qPrintable(s)); fflush(stdout);
    });
    QObject::connect(&recorder, &QMediaRecorder::recorderStateChanged, [&](QMediaRecorder::RecorderState s) {
        printf("STATE %d (frames sent %d accepted %d)\n", int(s), n, sent); fflush(stdout);
        if (s == QMediaRecorder::RecordingState) timer.start();
        if (s == QMediaRecorder::StoppedState) {
            printf("file %s\n", qPrintable(recorder.actualLocation().toLocalFile()));
            app.quit();
        }
    });
    recorder.record();
    QTimer::singleShot(240000, [&]() { printf("TIMEOUT\n"); app.quit(); });
    return app.exec();
}
