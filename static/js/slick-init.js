document.addEventListener('DOMContentLoaded', function () {
    var primarySlider = new Splide('#primary_slider', {
        type: 'fade',
        heightRatio: 1,
        pagination: false,
        arrows: false,
        cover: true,
    });

    var thumbnailSlider = new Splide('#thumbnail_slider', {
        rewind: true,
        fixedWidth: 150,
        fixedHeight: 150,
        isNavigation: true,
        gap: 10,
        focus: 'center',
        pagination: false,
        cover: true,
        breakpoints: {
            '600': {
                fixedWidth: 66,
                fixedHeight: 66,
            }
        }
    }).mount();

    primarySlider.sync(thumbnailSlider).mount();
});
