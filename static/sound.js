/* ============================================================
   تقييماتي — المؤثرات الصوتية بـ Tone.js
   أصوات خفيفة للأزرار واللايك ومؤقت المذاكرة (من غير موسيقى).
   لو المكتبة ما اتحمّلتش، الموقع بيشتغل عادي من غير صوت.
   ============================================================ */
(() => {
    if (!window.Tone) return;

    const KEY = "taqyimati_sound";
    const saved = (() => { try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { return {}; } })();
    const state = {
        fx: saved.fx !== false,                                   // المؤثرات شغالة افتراضيًا
        vol: Number.isFinite(saved.vol) ? saved.vol : 40,         // 0 - 100
    };
    const persist = () => {
        try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) { /* التخزين غير متاح */ }
    };

    const $ = (id) => document.getElementById(id);
    const widget = $("soundWidget"), panel = $("soundPanel"), fab = $("soundFab");
    const fxSw = $("fxSwitch"), volRange = $("volRange");
    if (!widget) return;
    widget.hidden = false;

    // ---------- المحرك ----------
    let ready = false, unlocking = null, synth;

    function applyVolume() {
        if (!ready) return;
        Tone.Destination.mute = state.vol === 0;
        Tone.Destination.volume.value = Tone.gainToDb(Math.max(state.vol, 1) / 100);
    }

    // لازم يتنادى من تفاعل المستخدم (ضغطة/لمسة) عشان المتصفح يسمح بالصوت
    function unlock() {
        if (ready) return Promise.resolve(true);
        if (!unlocking) {
            unlocking = Tone.start()
                .then(() => {
                    synth = new Tone.PolySynth(Tone.Synth, {
                        oscillator: { type: "triangle" },
                        envelope: { attack: 0.005, decay: 0.14, sustain: 0, release: 0.25 },
                    }).toDestination();
                    synth.volume.value = -12;
                    ready = true;
                    applyVolume();
                    return true;
                })
                .catch(() => { unlocking = null; return false; });
        }
        return unlocking;
    }

    // ---------- المؤثرات ----------
    const note = (n, len, at, vel) => synth.triggerAttackRelease(n, len, at, vel);
    const SFX = {
        tap()   { note("C6", "32n", Tone.now(), 0.5); },
        tick()  { note("E6", "32n", Tone.now(), 0.45); },
        like()  { const t = Tone.now(); note("E5", "16n", t, 0.6); note("B5", "8n", t + 0.09, 0.6); },
        start() { const t = Tone.now(); note("G5", "16n", t, 0.6); note("C6", "8n", t + 0.09, 0.6); },
        pause() { const t = Tone.now(); note("C6", "16n", t, 0.5); note("G5", "8n", t + 0.09, 0.5); },
        done()  { const t = Tone.now(); ["C5", "E5", "G5", "C6", "E6"].forEach((n, i) => note(n, "8n", t + i * 0.14, 0.7)); },
        error() { const t = Tone.now(); note("A3", "8n", t, 0.6); note("F3", "8n", t + 0.12, 0.6); },
    };

    async function play(name) {
        if (!state.fx || !SFX[name]) return;
        if (!(await unlock())) return;
        SFX[name]();
    }
    window.Sfx = { play };   // للاستخدام من صفحات تانية: Sfx.play("done")

    // صوت تلقائي للأزرار (ممكن تغيّره بـ data-sfx="اسم" أو data-sfx="none")
    document.addEventListener("click", (e) => {
        if (e.target.closest("#soundWidget")) return;
        const el = e.target.closest("[data-sfx], button, a.btn, .chip");
        if (!el) return;
        let name = el.dataset.sfx;
        if (!name) {
            if (el.classList.contains("btn-danger")) return;
            name = el.classList.contains("like") ? "like"
                 : el.classList.contains("chip") || el.classList.contains("menu-toggle") ? "tick"
                 : "tap";
        }
        if (name !== "none") play(name);
    });

    // ---------- واجهة التحكم ----------
    function syncUI() {
        fxSw.setAttribute("aria-checked", String(state.fx));
        volRange.value = state.vol;
        fab.classList.toggle("muted", !state.fx);
    }
    const closePanel = () => { panel.hidden = true; fab.setAttribute("aria-expanded", "false"); };

    fab.addEventListener("click", () => {
        panel.hidden = !panel.hidden;
        fab.setAttribute("aria-expanded", String(!panel.hidden));
    });
    document.addEventListener("click", (e) => {
        if (!panel.hidden && !e.target.closest("#soundWidget")) closePanel();
    });
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && !panel.hidden) { closePanel(); fab.focus(); }
    });

    fxSw.addEventListener("click", () => {
        state.fx = !state.fx;
        persist(); syncUI();
        if (state.fx) play("tick");
    });
    volRange.addEventListener("input", () => {
        state.vol = Number(volRange.value);
        applyVolume();
    });
    volRange.addEventListener("change", () => { persist(); play("tick"); });

    syncUI();
})();