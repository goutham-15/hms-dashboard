document.addEventListener('DOMContentLoaded', function() {
    // Theme Toggle
    initThemeToggle();
    
    fetchDashboardData();

    function initThemeToggle() {
        const themeToggle = document.getElementById('themeToggle');
        const body = document.body;
        
        // Check for saved theme preference or default to light
        const savedTheme = localStorage.getItem('theme') || 'light';
        if (savedTheme === 'dark') {
            body.classList.add('dark-theme');
        }
        
        themeToggle.addEventListener('click', function() {
            body.classList.toggle('dark-theme');
            const currentTheme = body.classList.contains('dark-theme') ? 'dark' : 'light';
            localStorage.setItem('theme', currentTheme);
        });
    }

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
        const moderateData = labels.map(l => ageData[l]['Moderate Risk'] || 0);
        const healthyData = labels.map(l => ageData[l]['Healthy']);

        new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    { label: 'Critical', data: criticalData, backgroundColor: '#ef4444' },
                    { label: 'High Risk', data: highData, backgroundColor: '#f59e0b' },
                    { label: 'Moderate', data: moderateData, backgroundColor: '#eab308' },
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
                <button class="review-btn" onclick="openReviewModal('${a.id}')">Review</button>
            `;
            list.appendChild(item);
        });
    }

    // Modal Control Functions
    function renderLabTable(groupName, tests) {
        if (!tests || tests.length === 0) return '';
        
        let rows = tests.map(t => `
            <tr>
                <td>${t.name}</td>
                <td><strong>${t.value}</strong> ${t.unit}</td>
                <td>${t.ref_range || '-'}</td>
                <td><span class="status-indicator ${t.status}">${t.status || 'Normal'}</span></td>
            </tr>
        `).join('');

        return `
            <div class="test-group-title">${groupName.replace('_', ' ')}</div>
            <table class="medical-table">
                <thead>
                    <tr><th>Test Name</th><th>Result</th><th>Ref Range</th><th>Status</th></tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        `;
    }

    function renderImagingCard(name, result) {
        if (!result || (!result.findings && !result.impression)) return '';
        
        return `
            <div class="imaging-card">
                <h4>${name.replace('_', ' ').toUpperCase()}</h4>
                <div class="imaging-text"><strong>Findings:</strong> ${result.findings || 'Not reported'}</div>
                <div class="imaging-text"><strong>Impression:</strong> ${result.impression || 'Not reported'}</div>
            </div>
        `;
    }

    window.openReviewModal = async function(recordId) {
        const modal = document.getElementById('healthModal');
        const modalBody = document.getElementById('modalBody');
        modalBody.innerHTML = '<div class="loading">Loading staff details...</div>';
        modal.style.display = 'flex';

        try {
            // Fetch the specific record (assuming the endpoint supports query by ID or we filter from all)
            const res = await fetch(`/api/v1/analytics/records`);
            const records = await res.json();
            const record = records.find(r => r.id === recordId);

            if (!record) {
                modalBody.innerHTML = '<div class="error">Record not found.</div>';
                return;
            }

            const statusClass = record.status.toLowerCase().replace(' ', '-');
            
            // Build Thyrocare sections
            const thyrocare = record.thyrocare_results || {};
            const labSections = Object.entries(thyrocare)
                .map(([name, tests]) => renderLabTable(name, tests))
                .join('');

            // Build SecondMedic sections
            const secondmedic = record.secondmedic_results || {};
            const imagingCards = Object.entries(secondmedic)
                .map(([name, result]) => renderImagingCard(name, result))
                .join('');

            modalBody.innerHTML = `
                <div class="review-grid">
                    <div class="staff-info-box">
                        <h3>Staff Profile</h3>
                        <div class="info-row"><span class="info-label">ID:</span> ${record.employee_id}</div>
                        <div class="info-row"><span class="info-label">Name:</span> ${record.name}</div>
                        <div class="info-row"><span class="info-label">Age:</span> ${record.age}</div>
                        <div class="info-row"><span class="info-label">Gender:</span> ${record.gender}</div>
                        <div class="info-row"><span class="info-label">Dept:</span> ${record.department}</div>
                        <div class="info-row"><span class="info-label">Date:</span> ${record.screening_date}</div>
                        
                        <div class="section-title" style="margin-top: 25px;">Summary</div>
                        <div class="findings-content">
                            ${record.inference || 'No clinical summary provided.'}
                        </div>
                    </div>
                    
                    <div class="findings-box">
                        <div>
                            <span class="status-tag ${statusClass}">${record.status}</span>
                            <div class="section-title">Active Risk Flags</div>
                            <div class="flags-container">
                                ${record.active_flags.map(f => `<span class="flag-chip">${f}</span>`).join('')}
                                ${record.active_flags.length === 0 ? '<span class="info-label">No high-risk flags identified.</span>' : ''}
                            </div>
                        </div>

                        <div>
                            <div class="section-title">Medical Suggestions</div>
                            <ul class="suggestions-list">
                                ${record.suggestion.map(s => `<li>${s}</li>`).join('')}
                                ${record.suggestion.length === 0 ? '<li>Maintain existing healthy lifestyle.</li>' : ''}
                            </ul>
                        </div>
                    </div>
                </div>

                <div class="medical-section">
                    <div class="section-title">Lab Test Results (Biochemical)</div>
                    ${labSections || '<div class="info-label">No lab results recorded in this session.</div>'}
                </div>

                <div class="medical-section">
                    <div class="section-title">Imaging & Diagnostic Findings</div>
                    <div class="imaging-grid">
                        ${imagingCards || '<div class="info-label">No imaging reports recorded in this session.</div>'}
                    </div>
                </div>
            `;
        } catch (error) {
            console.error('Error loading record:', error);
            modalBody.innerHTML = '<div class="error">Failed to load health details.</div>';
        }
    };

    window.closeModal = function() {
        document.getElementById('healthModal').style.display = 'none';
    };

    // Close on click outside
    window.onclick = function(event) {
        const modal = document.getElementById('healthModal');
        if (event.target == modal) {
            closeModal();
        }
    };

    function updateRecordsTable(records) {
        const tbody = document.querySelector('.health-table tbody');
        tbody.innerHTML = '';
        
        // Aggregate by department
        const depts = {};
        records.forEach(r => {
            const dept = r.department || 'General';
            if (!depts[dept]) {
                depts[dept] = {
                    count: 0,
                    critical: 0,
                    high: 0,
                    moderate: 0,
                    healthy: 0,
                    totalScore: 0,
                    topRisk: {}
                };
            }
            depts[dept].count++;
            if (r.status === 'Critical') depts[dept].critical++;
            else if (r.status === 'High Risk') depts[dept].high++;
            else if (r.status === 'Moderate Risk') depts[dept].moderate++;
            else if (r.status === 'Healthy') depts[dept].healthy++;
            
            depts[dept].totalScore += r.health_score || 0;
            
            if (r.active_flags && r.active_flags.length > 0) {
                const primaryFlag = r.active_flags[0];
                depts[dept].topRisk[primaryFlag] = (depts[dept].topRisk[primaryFlag] || 0) + 1;
            }
        });

        Object.keys(depts).forEach(deptName => {
            const d = depts[deptName];
            const avgScore = Math.round(d.totalScore / d.count);
            const topRiskEntry = Object.entries(d.topRisk).sort((a, b) => b[1] - a[1])[0];
            const topRiskStr = topRiskEntry ? topRiskEntry[0] : 'None';
            const overallStatus = d.critical > 0 ? 'critical' : (d.high > 0 ? 'warning' : 'on-track');

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${deptName}</td>
                <td>${d.count}</td>
                <td class="critical">${d.critical}</td>
                <td class="high">${d.high}</td>
                <td class="moderate">${d.moderate}</td>
                <td class="healthy">${d.healthy}</td>
                <td>${avgScore}/100</td>
                <td>${topRiskStr}</td>
                <td>100%</td>
                <td><span class="badge ${overallStatus}">${d.critical > 0 ? 'Critical' : (d.high > 0 ? 'High Risk' : 'On Track')}</span></td>
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

    // Export functionality
    const exportBtn = document.querySelector('.export-btn');
    if (exportBtn) {
        exportBtn.textContent = '↓ Export Excel'; // Match user request for excel
        exportBtn.addEventListener('click', function() {
            window.location.href = '/api/v1/analytics/export';
        });
    }
});
