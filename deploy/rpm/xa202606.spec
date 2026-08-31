Name:           xa202606-smart-factory
Version:        0.1.0
Release:        1%{?dist}
Summary:        Ontology-driven semantic interoperability platform for industrial IoT

License:        Proprietary
URL:            https://github.com/sensoumi4946-cpu/xa202606-smart-factory
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3 >= 3.11
BuildRequires:  python3-pip
Requires:       python3 >= 3.11
Requires:       systemd

%description
XA-202606 exposes industrial device bindings as a system service. Register
addresses, scale factors, byte order, poll intervals and OPC UA node ids are
declared once as ontology triples; protocol adapter logic is generated from
those triples rather than written by hand.

The binding service answers device identity and access queries over a Unix
domain socket, so any process on the host can resolve a device without linking
against the platform.

%prep
%setup -q

%build
python3 -m venv %{_builddir}/venv
%{_builddir}/venv/bin/pip install --upgrade pip
%{_builddir}/venv/bin/pip install ./shared ./semantic-layer ./backend ./connectivity ./analytics

%install
mkdir -p %{buildroot}/opt/xa202606
cp -a %{_builddir}/venv %{buildroot}/opt/xa202606/venv

mkdir -p %{buildroot}%{_sysconfdir}/xa202606
install -m 0644 bindings.ttl %{buildroot}%{_sysconfdir}/xa202606/bindings.ttl

mkdir -p %{buildroot}%{_unitdir}
install -m 0644 deploy/systemd/xa202606-bindingd.service %{buildroot}%{_unitdir}/
install -m 0644 deploy/systemd/xa202606-bindingd.socket  %{buildroot}%{_unitdir}/
install -m 0644 deploy/systemd/xa202606-backend.service  %{buildroot}%{_unitdir}/

mkdir -p %{buildroot}%{_bindir}
ln -s /opt/xa202606/venv/bin/sf-binding %{buildroot}%{_bindir}/sf-binding

mkdir -p %{buildroot}%{_sharedstatedir}/xa202606

%pre
getent group xa202606 >/dev/null || groupadd -r xa202606
getent passwd xa202606 >/dev/null || \
    useradd -r -g xa202606 -d /opt/xa202606 -s /sbin/nologin \
            -c "XA-202606 platform" xa202606
exit 0

%post
%systemd_post xa202606-bindingd.socket xa202606-bindingd.service xa202606-backend.service

%preun
%systemd_preun xa202606-bindingd.socket xa202606-bindingd.service xa202606-backend.service

%postun
%systemd_postun_with_restart xa202606-bindingd.service xa202606-backend.service

%files
/opt/xa202606
%{_bindir}/sf-binding
%{_unitdir}/xa202606-bindingd.service
%{_unitdir}/xa202606-bindingd.socket
%{_unitdir}/xa202606-backend.service
%config(noreplace) %{_sysconfdir}/xa202606/bindings.ttl
%dir %attr(0750,xa202606,xa202606) %{_sharedstatedir}/xa202606

%changelog
* Sun Aug 30 2026 XA-202606 Team <team@xa202606.local> - 0.1.0-1
- Initial packaging: binding service, backend, CLI, systemd units