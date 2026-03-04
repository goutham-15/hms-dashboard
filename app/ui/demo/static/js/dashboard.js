document.addEventListener('DOMContentLoaded', function() {
    fetchDashboardData();

    async function fetchDashboardData() {
        try {
            // Fetch Summary
            const summaryRes = await fetch('/api/v1/analytics/summary');
            const summary = await summaryRes.json();
            updateSummaryCards(summary);

            // Fetch Stats (Charts)
            const statsRes = await fetch('/api/v1/analytics/stats');
            const stats = await statsRes.json();
            initDonutChart(stats.status_distribution);
            initAgeBarChart(stats.age_risk);
            updateFlaggedConditions(stats.top_conditions);
            updateDepartmentDistribution(stats.department_distribution);
            updateGenderComparison(stats.gender_comparison);

            // Fetch Alerts
            const alertsRes = await fetch('/api/v1/analytics/alerts');
            const alerts = await alertsRes.json();
            updateAlerts(alerts);

            // Fetch Records for Table
            const recordsRes = await fetch('/api/v1/analytics/records');
            const records = await recordsRes.json();
            updateRecordsTable(records);

        } catch (error) {
            console.error('Error fetching dashboard data:', error);
        }
    }

    function updateSummaryCards(data) {
        document.getElementById('totalFaculty').textContent = data.total_faculty;
        document.getElementById('criticalCount').textContent = data.critical;
        document.getElementById('highRiskCount').textContent = data.high_risk;
        document.getElementById('moderateRiskCount').textContent = data.moderate;
        document.getElementById('healthyCount').textContent = data.healthy;
        document.getElementById('avgHealthScore').textContent = data.avg_health_score;
    }

    function updateDepartmentDistribution(depts) {
        const list = document.getElementById('deptRiskList');
        if (!list) return;
        list.innerHTML = '';
        
        Object.keys(depts).forEach(deptName => {
            const data = depts[deptName];
            const critPct = Math.round((data['Critical'] / data.total) * 100);
            const highPct = Math.round((data['High Risk'] / data.total) * 100);
            const modPct = Math.round((data['Moderate Risk'] / data.total) * 100);
            const healthPct = 100 - (critPct + highPct + modPct);
            
            const item = document.createElement('div');
            item.className = 'dept-item';
            item.innerHTML = `
                <div class="dept-header">
                    <span class="dept-name">${deptName}</span>
                    <span class="dept-count">${data.total} faculty</span>
                </div>
                <div class="progress-bar-group">
                    ${critPct > 0 ? `<div class="progress-segment critical" style="width: ${critPct}%">${critPct}%</div>` : ''}
                    ${highPct > 0 ? `<div class="progress-segment high" style="width: ${highPct}%">${highPct}%</div>` : ''}
                    ${modPct > 0 ? `<div class="progress-segment moderate" style="width: ${modPct}%">${modPct}%</div>` : ''}
                    ${healthPct > 0 ? `<div class="progress-segment healthy" style="width: ${healthPct}%">${healthPct}%</div>` : ''}
                </div>
            `;
            list.appendChild(item);
        });
    }

    function initDonutChart(dist) {
        const ctx = document.getElementById('healthDonutChart').getContext('2d');
        new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Critical', 'High Risk', 'Moderate', 'Healthy'],
                datasets: [{
                    data: [dist['Critical'], dist['High Risk'], dist['Moderate Risk'], dist['Healthy']],
                    backgroundColor: ['#ef4444', '#f59e0b', '#eab308', '#10b981'],
                    borderWidth: 0,
                    cutout: '75%'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } }
            }
        });
        
        // Update total in center of donut
        const total = Object.values(dist).reduce((a, b) => a + b, 0);
        document.querySelector('.total-val').textContent = total;

        // Update legend values
        document.getElementById('legendCritical').textContent = dist['Critical'] || 0;
        document.getElementById('legendHigh').textContent = dist['High Risk'] || 0;
        document.getElementById('legendModerate').textContent = dist['Moderate Risk'] || 0;
        document.getElementById('legendHealthy').textContent = dist['Healthy'] || 0;
    }

    function initAgeBarChart(ageData) {
        const ctx = document.getElementById('ageRiskChart').getContext('2d');
        const labels = Object.keys(ageData);
        const criticalData = labels.map(l => ageData[l]['Critical']);
        const highData = labels.map(l => ageData[l]['High Risk']);
        const healthyData = labels.map(l => ageData[l]['Healthy']);

        new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    { label: 'Critical', data: criticalData, backgroundColor: '#ef4444' },
                    { label: 'High Risk', data: highData, backgroundColor: '#f59e0b' },
                    { label: 'Healthy', data: healthyData, backgroundColor: '#10b981' }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { stacked: true, grid: { display: false } },
                    y: { stacked: true, grid: { color: '#2d334a' } }
                },
                plugins: { legend: { display: false } }
            }
        });
    }

    function updateFlaggedConditions(conditions) {
        const list = document.querySelector('.flagged-list');
        list.innerHTML = '';
        conditions.forEach(c => {
            const item = document.createElement('div');
            item.className = 'flag-item';
            item.innerHTML = `
                <span class="flag-name">${c.name}</span>
                <span class="flag-val">${c.count}</span>
                <div class="flag-bar" style="width: ${Math.min(c.count * 20, 100)}%"></div>
            `;
            list.appendChild(item);
        });
    }

    function updateGenderComparison(genderStats) {
        const male = genderStats['MALE'] || { count: 0, total_score: 0, high_risk: 0 };
        const female = genderStats['FEMALE'] || { count: 0, total_score: 0, high_risk: 0 };

        const maleAvg = male.count > 0 ? Math.round(male.total_score / male.count) : 0;
        const femaleAvg = female.count > 0 ? Math.round(female.total_score / female.count) : 0;

        document.getElementById('maleCount').textContent = `Male (${male.count})`;
        document.getElementById('femaleCount').textContent = `Female (${female.count})`;

        document.getElementById('maleGauge').style.setProperty('--pct', maleAvg);
        document.getElementById('femaleGauge').style.setProperty('--pct', femaleAvg);

        const footer = document.getElementById('genderFooter');
        if (male.count > 0 && female.count > 0) {
            const maleRiskPct = Math.round((male.high_risk / male.count) * 100);
            const femaleRiskPct = Math.round((female.high_risk / female.count) * 100);
            
            if (maleRiskPct > femaleRiskPct) {
                footer.textContent = `Males show ${maleRiskPct - femaleRiskPct}% higher health risk`;
            } else if (femaleRiskPct > maleRiskPct) {
                footer.textContent = `Females show ${femaleRiskPct - maleRiskPct}% higher health risk`;
            } else {
                footer.textContent = `Health risk is equal across genders`;
            }
        }
    }

    function updateAlerts(alerts) {
        const list = document.querySelector('.alert-list');
        const alertCount = document.getElementById('alertCount');
        const totalAlertsLink = document.getElementById('totalAlertsLink');
        const headerBadge = document.getElementById('headerBadge');
        
        if (alertCount) alertCount.textContent = alerts.length;
        if (totalAlertsLink) totalAlertsLink.textContent = alerts.length;
        if (headerBadge) headerBadge.textContent = alerts.length;
        
        if (!list) return;
        list.innerHTML = '';
        alerts.forEach(a => {
            const item = document.createElement('div');
            item.className = 'alert-item';
            const initials = a.name.split(' ').map(n => n[0]).join('').substring(0, 2);
            item.innerHTML = `
                <div class="alert-avatar sm">${initials}</div>
                <div class="alert-content">
                    <h4>${a.name} (${a.department})</h4>
                    <p>${a.active_flags.join(', ')}</p>
                    <span class="time">${a.screening_date}</span>
                </div>
                <button class="review-btn" onclick="alert('Reviewing ${a.name}')">Review</button>
            `;
            list.appendChild(item);
        });
    }

    function updateRecordsTable(records) {
        const tbody = document.querySelector('.health-table tbody');
        tbody.innerHTML = '';
        records.forEach(r => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${r.department}</td>
                <td>1</td>
                <td class="${r.status === 'Critical' ? 'critical' : ''}">${r.status === 'Critical' ? 1 : 0}</td>
                <td class="${r.status === 'High Risk' ? 'high' : ''}">${r.status === 'High Risk' ? 1 : 0}</td>
                <td class="${r.status === 'Moderate Risk' ? 'moderate' : ''}">${r.status === 'Moderate Risk' ? 1 : 0}</td>
                <td class="${r.status === 'Healthy' ? 'healthy' : ''}">${r.status === 'Healthy' ? 1 : 0}</td>
                <td>${r.health_score}/100</td>
                <td>${r.active_flags[0] || 'None'}</td>
                <td>100%</td>
                <td><span class="badge ${r.status === 'Healthy' ? 'on-track' : 'warning'}">${r.status}</span></td>
            `;
            tbody.appendChild(tr);
        });
    }

    // Search functionality
    const searchInput = document.querySelector('.search-input');
    if (searchInput) {
        searchInput.addEventListener('input', async function(e) {
            const query = e.target.value;
            const res = await fetch(`/api/v1/analytics/records?query=${query}`);
            const records = await res.json();
            updateRecordsTable(records);
        });
    }
});
