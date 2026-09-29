document.addEventListener("DOMContentLoaded", () => {
    // ---- قائمة الموبايل ----
    const toggle = document.getElementById("menuToggle");
    const nav = document.getElementById("nav");
    if (toggle && nav) toggle.addEventListener("click", () => nav.classList.toggle("open"));

    // ---- إخفاء رسائل التنبيه تلقائيًا ----
    document.querySelectorAll(".alerts .alert").forEach((a) => {
        setTimeout(() => {
            a.style.transition = "opacity .5s";
            a.style.opacity = "0";
            setTimeout(() => a.remove(), 500);
        }, 4500);
    });

    // ---- بحث وفلترة بالمادة (صفحات التقييمات والواجبات) ----
    const groups = [...document.querySelectorAll(".group")];
    if (groups.length) {
        const search = document.getElementById("search");
        const chips = [...document.querySelectorAll(".chip")];
        const noResults = document.getElementById("noResults");
        let subject = "";

        const apply = () => {
            const q = (search ? search.value : "").trim().toLowerCase();
            let any = false;
            groups.forEach((g) => {
                const subjectOk = !subject || g.dataset.subject === subject;
                let shown = 0;
                g.querySelectorAll(".item").forEach((it) => {
                    const ok = subjectOk && (!q || it.dataset.title.toLowerCase().includes(q));
                    it.style.display = ok ? "" : "none";
                    if (ok) shown++;
                });
                g.style.display = shown ? "" : "none";
                if (shown) any = true;
            });
            if (noResults) noResults.style.display = any ? "none" : "block";
        };

        chips.forEach((c) =>
            c.addEventListener("click", () => {
                chips.forEach((x) => x.classList.remove("active"));
                c.classList.add("active");
                subject = c.dataset.subject;
                apply();
            })
        );
        if (search) search.addEventListener("input", apply);

        // فتح مادة معينة من الصفحة الرئيسية (?subject=...)
        const wanted = new URLSearchParams(location.search).get("subject");
        if (wanted) {
            const chip = chips.find((x) => x.dataset.subject === wanted);
            if (chip) chip.click();
        }
    }

    // ---- زر مشاركة الموقع مع الأصحاب ----
    const shareBtn = document.getElementById("shareBtn");
    if (shareBtn) {
        shareBtn.addEventListener("click", async () => {
            const data = {
                title: "تقييماتي",
                text: "تعالى نذاكر سوا! كل التقييمات والواجبات في مكان واحد",
                url: location.origin,
            };
            try {
                if (navigator.share) {
                    await navigator.share(data);
                } else {
                    await navigator.clipboard.writeText(location.origin);
                    shareBtn.innerHTML = '<svg class="ic" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg> اتنسخ الرابط';
                }
            } catch (e) { /* المستخدم لغى المشاركة */ }
        });
    }
});