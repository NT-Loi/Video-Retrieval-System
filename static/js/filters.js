import { elements } from './elements.js';

export function initFilters() {
    // Toggle Advanced Filters
    elements.toggleFiltersBtn.addEventListener('click', () => {
        elements.advancedFilters.classList.toggle('hidden');
        elements.toggleFiltersBtn.textContent = elements.advancedFilters.classList.contains('hidden') 
            ? '▼ Advanced Filters' 
            : '▲ Hide Filters';
    });

    // Add Object to List
    elements.addObjectBtn.addEventListener('click', () => {
        const label = elements.objectSelect.value;
        const min = elements.objectMin.value;
        const max = elements.objectMax.value;
        const confidence = elements.objectConfidence.value;

        if (document.querySelector(`.object-item[data-label="${label}"]`)) {
            alert('Object already added.');
            return;
        }

        const objectItem = document.createElement('div');
        objectItem.classList.add('object-item');
        objectItem.setAttribute('data-label', label);
        objectItem.setAttribute('data-min', min);
        objectItem.setAttribute('data-max', max);
        objectItem.setAttribute('data-confidence', confidence);

        let countText;
        if (!max || max.trim() === '') {
            countText = `Count: >= ${min}`;
        } else {
            countText = `Count: [${min}, ${max}]`;
        }

        objectItem.innerHTML = `<span>${label} (Confidence: >= ${confidence}, ${countText})</span><button type="button" class="remove-obj-btn">X</button>`;
        elements.objectList.appendChild(objectItem);
    });

    // Remove Object from List
    elements.objectList.addEventListener('click', (e) => {
        if (e.target.classList.contains('remove-obj-btn')) {
            e.target.parentElement.remove();
        }
    });
}

export function getObjectQueries() {
    const objects = [];
    document.querySelectorAll('.object-item').forEach(item => {
        const objectQuery = {
            label: item.getAttribute('data-label'),
            confidence: parseFloat(item.getAttribute('data-confidence')),
            min_instances: parseInt(item.getAttribute('data-min'), 10)
        };
        const maxInstancesValue = item.getAttribute('data-max');
        if (maxInstancesValue) {
            objectQuery.max_instances = parseInt(maxInstancesValue, 10);
        }
        objects.push(objectQuery);
    });
    return objects;
}
