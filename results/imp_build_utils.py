import glob
import datetime
import pickle
import os
import MySQLdb
import collections
try:
    from email.Utils import formatdate  # python2
    from email.MIMEText import MIMEText
except ImportError:
    from email.utils import formatdate  # python3
    from email.mime.text import MIMEText


OK_STATES = ('OK', 'SKIP', 'EXPFAIL', 'SKIP_EXPFAIL')
lab_only_results_url = 'https://salilab.org/internal/imp/nightly/results/'
results_url = 'https://integrativemodeling.org/nightly/results/'

# Special components are build steps that do not correspond to IMP modules,
# applications, or biological systems. They are only 'built', never tested
# or benchmarked.
SPECIAL_COMPONENTS = {'ALL': 'Entire cmake and make',
                      'ALL_LAB':
                      'Entire cmake and make of lab-only components',
                      'INSTALL': 'Installation of all of IMP',
                      'INSTALL_LAB': 'Installation of lab-only components',
                      'DOC': 'Build and install of documentation',
                      'RMF-DOC': 'Build and install of RMF documentation',
                      'PACKAGE': 'Build of binary package',
                      'OPENMPI': 'Rebuild of IMP.mpi module against '
                                 'different versions of OpenMPI',
                      'COVERAGE': 'Coverage of C++ and Python code',
                      'COVERAGE_LAB': 'Coverage of C++ and Python code '
                                      'in lab-only components'}


class Platform(object):
    def __init__(self, very_short, short, long, very_long, logfile):
        self.very_short = very_short
        self.short = short
        self.long = long
        self.very_long = very_long
        self.logfile = logfile


rpm_vlong_header = """
<p>This platform builds and tests the IMP RPM package on a fully updated
%s system. The actual build is done in a
<a href="https://github.com/rpm-software-management/mock/wiki">mock</a>
environment.</p>
"""
rpm_vlong_footer = """
<p>To build an RPM package yourself, you can rebuild from the source RPM
(available at the
<a href="https://integrativemodeling.org/download-linux.html">download
page</a>) or use the spec file in the
<a href="https://github.com/salilab/imp/tree/develop/tools/rpm">tools/rpm/</a>
directory. Note that you will
need some extra nonstandard RPM packages to reproduce our builds:
<a href="https://salilab.org/modeller/">modeller</a>,
<a href="https://integrativemodeling.org/libTAU.html">libTAU,
libTAU-devel</a>, and other dependencies available at
<a href="https://integrativemodeling.org/build-extras/">https://integrativemodeling.org/build-extras/</a>.
"""

rpm_cvlong = rpm_vlong_header + """
<p>The resulting package should install on a CentOS or RedHat Enterprise
machine with the <a href="https://fedoraproject.org/wiki/EPEL">EPEL
repository</a>.</p>
""" + rpm_vlong_footer + "%s"

rpm_centos5 = """In particular, the versions of cmake, HDF5 and SWIG that ship
with CentOS 5 are too old for IMP. We provide newer versions."""

debug_build_vlong = """
<p>This is a <b>debug</b> build, built with all checks turned on
(<tt>IMP_MAX_CHECKS=INTERNAL</tt> cmake option). This is so that the tests
can be as thorough as possible. The resulting code is much slower, however,
so the IMP tests marked EXPENSIVE are skipped (they are run in fast
builds).</p>
"""
fast_build_vlong = """
<p>This is a <b>fast</b> build, built with all checks and logging turned off
(<tt>IMP_MAX_CHECKS=NONE</tt> and <tt>IMP_MAX_LOG=SILENT</tt> cmake options).
This gives the fastest running code, so even tests marked EXPENSIVE are
run with this build. However, the lack of runtime error checking means that
test failures may be hard to diagnose (IMP may segfault rather than
reporting an error).</p>
"""
fast_build_module_vlong = fast_build_vlong + """
<p>In the Sali lab, fast builds can be used on the cluster or Linux
workstations by running <tt>module load imp-fast</tt>. Work out all the
bugs first though!</p>
"""

release_build_module_vlong = """
<p>This is a <b>release</b> build, built with only usage checks turned on.
This gives code that is almost as fast as a 'fast' build, without sacrificing
logging or error checking (the binary installer packages are similar). Such
builds should be preferred for all but the most compute-intensive tasks.
</p>

<p>In the Sali lab, this build can be used on the cluster or Linux workstations
by running <tt>module load imp</tt>.</p>
"""

windows_vlong = """
<p>This platform builds and tests IMP for %s Windows, and also builds a
<tt>.exe</tt> installer. It does not actually run on a real Windows machine;
it runs on a Linux box and runs the real Windows binaries for the C++ compiler,
Python, and the built IMP itself via <a href="https://winehq.org/">WINE</a>.
(We do this to more easily integrate with our Linux systems.)
</p>

<p>To build the .exe package yourself, see the
<a href="https://github.com/salilab/imp/tree/develop/tools/w32">tools/w32/</a>
directory, in particular the <tt>make-package.sh</tt> script.</p>

<p>It should also be possible to build IMP on a real Windows machine;
instructions are in the IMP documentation. If it doesn't work, let us know
and we'll fix it!</p>
"""

mac_header = """
<p>This platform builds and tests IMP on a %s system with %s. This is a
standard Mac with XCode installed plus <a href="https://brew.sh/">Homebrew</a>,
the <tt>salilab/salilab</tt> Homebrew tap, and
the following Homebrew packages: <tt>boost</tt>, <tt>cgal</tt>, <tt>cmake</tt>,
<tt>doxygen</tt>, <tt>hdf5</tt>, <tt>libtau</tt>, <tt>ninja</tt>,
<tt>opencv</tt>, <tt>protobuf</tt>, and <tt>swig</tt>.
</p>
"""
mac_vlong = mac_header + debug_build_vlong

macpkg_vlong = """
<p>This platform also builds the Mac .dmg installer package. This is built from
the same IMP code but with only usage checks turned on (the resulting code
is much faster than that with internal checks).</p>

<p>To build the package yourself, see the
<a href="https://github.com/salilab/imp/tree/develop/tools/mac">tools/mac/</a>
directory, in particular the <tt>make-package.sh</tt> script.</p>
"""

percpp_vlong = """
<p>Most IMP builds do batch compilation, where the compiler handles all the
<tt>.cpp</tt> files for a module at once. However, IMP also supports a
"per-cpp" mode where each <tt>.cpp</tt> file is compiled individually (the
<tt>IMP_PER_CPP_COMPILATION</tt> cmake option). This mode is less tolerant
of missing <tt>#include</tt> statements and other programming errors.
This platform builds IMP in this mode to detect such errors.
</p>
"""

mac109_vlong = """
<p>Note that occasionally the build does not run at all on this platform
(yellow boxes in the build summary). This is because the cronjob on this
machine sometimes doesn't get started. This appears to be a bug in OS X 10.9.
</p>
"""

ubuntu_vlong = """
<p>This platform builds and tests the IMP Debian/Ubuntu (<tt>.deb</tt>) package
on 64-bit Ubuntu %s (running inside a
<a href="https://www.docker.com/">Docker</a> container).</p>

<p>To build the package yourself, see the
<a href="https://github.com/salilab/imp/tree/develop/tools/debian">tools/debian/</a>
directory, in particular the <tt>make-package.sh</tt> script.</p>
"""

linux_vlong = """
<p>This platform builds and tests IMP on a fully updated %s system.%s
The system is customized with additional RPM packages so that all IMP modules
and applications can be built and tested (in contrast to the RPM builds, where
only those modules and applications that use packages in the RedHat
repositories are built).
</p>
%s
"""

cuda_vlong = """
<p>This platform builds and tests IMP on a fully updated %s system with
the CUDA toolkit and Python 3, and activates IMP's <b>experimental</b> GPU
code.</p>
"""

coverage_vlong = """
<p>This platform builds and tests IMP on a fully updated %s system with
Python 3, and collects coverage information. This information is reported for
both Python and C++ code, for modules and applications, on the far right side
of the build summary page.</p>

<p>
For more information on coverage reporting, see the
<a href="https://github.com/salilab/imp/tree/develop/tools/coverage">tools/coverage/</a>
directory.
</p>
%s
"""

static_vlong = """
<p>This platform builds IMP on a fully updated %s system, but unlike
regular builds, links every binary statically (<tt>IMP_STATIC</tt> cmake
option). Note that many modules do not support static linking and thus are
excluded from this build. Also, since Python requires dynamic linking, no
Python modules are built or tests run.
</p>
"""

openmp_vlong = """
It is built with <a href="http://openmp.org/">OpenMP</a> support
(<tt>-fopenmp</tt> compiler flag) to test IMP parallel code.
"""

openmpi_vlong = """
It is built with <a href="http://www.mpi-forum.org/">MPI</a> support
(<tt>mpicc</tt> and <tt>mpic++</tt>
<a href="https://www.open-mpi.org/">OpenMPI</a> compilers) to test IMP
parallel code.
"""

all_platforms = (
    ('i386-intel8',
     Platform('Lin32', 'Linux32',
              'Debug build (32-bit Linux; CentOS 6.10 on i686; Boost 1.41)',
              linux_vlong % ("32-bit CentOS 6.10", '', debug_build_vlong),
              'bin.i386-intel8.log')),
    ('x86_64-intel8',
     Platform('Lin64', 'Linux64',
              'Debug build (64-bit Linux; CentOS 7.7 on x86_64; Boost 1.53)',
              linux_vlong % ("64-bit CentOS 7.7", '', debug_build_vlong),
              'bin.x86_64-intel8.log')),
    ('mac10v4-intel',
     Platform('Mac', 'Mac 10.4',
              '32-bit Intel Mac (MacOS X 10.4 (Tiger), 32 bit; Boost 1.47)',
              '', 'bin.mac10v4-intel.log')),
    ('mac10v4-intel64',
     Platform('M10.6', 'Mac 10.6',
              'Debug build (64-bit Intel Mac; MacOS X 10.6 '
              '(Snow Leopard); Boost 1.59; Python 2)',
              mac_vlong % ("64-bit 10.6 (Snow Leopard) Mac",
                           "Apple's Python 2") + macpkg_vlong,
              'bin.mac10v4-intel64.log')),
    ('mac10v8-intel',
     Platform('M10.8', 'Mac 10.8',
              'Debug build (64-bit Intel Mac; MacOS X 10.8 '
              '(Mountain Lion); clang++; Boost 1.55; per-cpp compilation)',
              mac_vlong % ("64-bit 10.8 (Mountain Lion) Mac",
                           "Homebrew Python 2") + percpp_vlong,
              'bin.mac10v8-intel.log')),
    ('mac10v9-intel',
     Platform('M10.9', 'Mac 10.9',
              'Debug build (64-bit Intel Mac; MacOS X 10.9 '
              '(Mavericks); clang++; Boost 1.58)',
              mac_vlong % ("64-bit 10.9 (Mavericks) Mac",
                           "Homebrew Python 2") + mac109_vlong,
              'bin.mac10v9-intel.log')),
    ('mac10v10-intel',
     Platform('M10.10', 'Mac 10.10',
              'Debug build (64-bit Intel Mac; MacOS X 10.10 (Yosemite); '
              'clang++; Boost 1.67; Python 3; per-cpp compilation)',
              mac_vlong % ("64-bit 10.10 (Yosemite) Mac",
                           "Homebrew Python 3") + percpp_vlong,
              'bin.mac10v10-intel.log')),
    ('mac10v11-intel',
     Platform('M10.11', 'Mac 10.11',
              'Debug build (64-bit Intel Mac; MacOS X 10.11 '
              '(El Capitan); clang++; Boost 1.67; Python 3)',
              mac_vlong % ("64-bit 10.11 (El Capitan) Mac",
                           "Homebrew Python 3"),
              'bin.mac10v11-intel.log')),
    ('i386-w32',
     Platform('Win32', 'Windows',
              '32-bit Windows build (WINE 2.20, MSVC++ 2010 '
              'Express, Boost 1.53)', windows_vlong % "32-bit",
              'bin.i386-w32.log')),
    ('x86_64-w64',
     Platform('Win64', 'Windows64',
              '64-bit Windows build (WINE 2.20, MSVC++ 2012 '
              'Express, Boost 1.55)', windows_vlong % "64-bit",
              'bin.x86_64-w64.log')),
    ('fast',
     Platform('Fst32', 'Fast32',
              'Fast build (32-bit Linux, CentOS 6.10, Boost 1.41)',
              linux_vlong % ("32-bit CentOS 6.10", '',
                             fast_build_module_vlong),
              'bin-fast.i386-intel8.log')),
    ('fast64',
     Platform('Fst64', 'Fast64',
              'Fast build (64-bit Linux, CentOS 7.7, Boost 1.53)',
              linux_vlong % ("64-bit CentOS 7.7", '', fast_build_module_vlong),
              'bin-fast.x86_64-intel8.log')),
    ('release64',
     Platform('Rls64', 'Rls64',
              'Release build (64-bit Linux, CentOS 7.7, Boost 1.53)',
              linux_vlong % ("64-bit CentOS 7.7", '',
                             release_build_module_vlong),
              'bin-release.x86_64-intel8.log')),
    ('cuda',
     Platform('CUDA', 'CUDA',
              'CUDA build (64-bit Linux, Fedora 31, gcc 9.2, '
              'Boost 1.69, CUDA toolkit 10.0, Python 3)',
              cuda_vlong % "64-bit Fedora 31",
              'bin-cuda.log')),
    ('openmp',
     Platform('OMP', 'OpenMP',
              'OpenMP build (64-bit Linux, CentOS 6.10, Boost 1.41)',
              linux_vlong % ("64-bit CentOS 6.10", openmp_vlong,
                             debug_build_vlong),
              'openmp.x86_64-intel8.log')),
    ('fastmac',
     Platform('FstMc', 'FastMac',
              'Fast build (MacOS X 10.8 (Mountain Lion), '
              '64 bit; clang++; Boost 1.55)',
              mac_header % ("64-bit 10.8 (Mountain Lion) Mac",
                            "Homebrew Python 2") + fast_build_vlong,
              'bin-fast.mac10v8-intel.log')),
    ('fastmac10v10',
     Platform('FstMc', 'FastMac',
              'Fast build (MacOS X 10.10 (Yosemite), '
              '64 bit; clang++; Boost 1.66)',
              mac_header % ("64-bit 10.10 (Yosemite) Mac",
                            "Homebrew Python 3") + fast_build_vlong,
              'bin-fast.mac10v10-intel.log')),
    ('fastmpi',
     Platform('MPI', 'FastMPI',
              'Fast build (64-bit Linux, OpenMPI 1.5.4, CentOS 6.10, '
              'Boost 1.41)',
              linux_vlong % ("64-bit CentOS 6.10", openmpi_vlong,
                             fast_build_vlong),
              'bin-fast.x86_64-intel8.mpi.log')),
    ('static',
     Platform('Stat', 'Static',
              'Static build (x86_64 Linux, CentOS 7.7, Boost 1.53)',
              static_vlong % "64-bit CentOS 7.7",
              'bin-static.x86_64-intel8.log')),
    ('pkg.el5-i386',
     Platform('RH5_3', 'RH5_32',
              'RedHat Enterprise/CentOS 5.11 32-bit RPM build; Boost 1.41',
              rpm_cvlong % ("32-bit CentOS 5.11", rpm_centos5),
              'package.el5-i386.log')),
    ('pkg.el5-x86_64',
     Platform('RH5_6', 'RH5_64',
              'RedHat Enterprise/CentOS 5.11 64-bit RPM build; Boost 1.41',
              rpm_cvlong % ("64-bit CentOS 5.11", rpm_centos5),
              'package.el5-x86_64.log')),
    ('pkg.el6-i386',
     Platform('RH6_3', 'RH6_32',
              'RedHat Enterprise/CentOS 6.10 32-bit RPM build; Boost 1.41',
              rpm_cvlong % ("32-bit CentOS 6.10", ""),
              'package.el6-i386.log')),
    ('pkg.el6-x86_64',
     Platform('RH6_6', 'RH6_64',
              'RedHat Enterprise/CentOS 6.10 64-bit RPM build; Boost 1.41',
              rpm_cvlong % ("64-bit CentOS 6.10", ""),
              'package.el6-x86_64.log')),
    ('pkg.el7-x86_64',
     Platform('RH7_6', 'RH7_64',
              'RedHat Enterprise/CentOS 7.7 64-bit RPM build; Boost 1.53',
              rpm_cvlong % ("64-bit CentOS 7.7", ""),
              'package.el7-x86_64.log')),
    ('pkg.el8-x86_64',
     Platform('RH8_6', 'RH8_64',
              'RedHat Enterprise/CentOS 8.0 64-bit RPM build; '
              'Boost 1.66, Python 3',
              rpm_cvlong % ("64-bit CentOS 8.0", ""),
              'package.el8-x86_64.log')),
    ('pkg.f16-x86_64',
     Platform('F16', 'F16 RPM',
              'Fedora 16 64-bit RPM; Boost 1.47, gcc 4.6',
              '', 'package.fc16-x86_64.log')),
    ('pkg.f17-x86_64',
     Platform('F17', 'F17 RPM',
              'Fedora 17 64-bit RPM; Boost 1.48, gcc 4.7',
              '', 'package.fc17-x86_64.log')),
    ('pkg.f18-x86_64',
     Platform('F18', 'F18 RPM',
              'Fedora 18 64-bit RPM; Boost 1.50, gcc 4.7',
              '', 'package.fc18-x86_64.log')),
    ('pkg.f19-x86_64',
     Platform('F19', 'F19 RPM',
              'Fedora 19 64-bit RPM; Boost 1.53, gcc 4.8',
              '', 'package.fc19-x86_64.log')),
    ('pkg.f20-x86_64',
     Platform('F20', 'F20 RPM',
              'Fedora 20 64-bit RPM build; Boost 1.54, gcc 4.8',
              rpm_vlong_header % "64-bit Fedora 20"
              + rpm_vlong_footer + "</p>",
              'package.fc20-x86_64.log')),
    ('pkg.f21-x86_64',
     Platform('F21', 'F21 RPM',
              'Fedora 21 64-bit RPM build; Boost 1.55, gcc 4.9',
              rpm_vlong_header % "64-bit Fedora 21"
              + rpm_vlong_footer + "</p>",
              'package.fc21-x86_64.log')),
    ('pkg.f22-x86_64',
     Platform('F22', 'F22 RPM',
              'Fedora 22 64-bit RPM build; Boost 1.57, gcc 5.1',
              rpm_vlong_header % "64-bit Fedora 22"
              + rpm_vlong_footer + "</p>",
              'package.fc22-x86_64.log')),
    ('pkg.f23-x86_64',
     Platform('F23', 'F23 RPM',
              'Fedora 23 64-bit RPM build; Boost 1.58, gcc 5.1',
              rpm_vlong_header % "64-bit Fedora 23"
              + rpm_vlong_footer + "</p>",
              'package.fc23-x86_64.log')),
    ('pkg.f24-x86_64',
     Platform('F24', 'F24 RPM',
              'Fedora 24 64-bit RPM build; Boost 1.60, gcc 6.2',
              rpm_vlong_header % "64-bit Fedora 24"
              + rpm_vlong_footer + "</p>",
              'package.fc24-x86_64.log')),
    ('pkg.f25-x86_64',
     Platform('F25', 'F25 RPM',
              'Fedora 25 64-bit RPM build; Boost 1.60, gcc 6.2',
              rpm_vlong_header % "64-bit Fedora 25"
              + rpm_vlong_footer + "</p>",
              'package.fc25-x86_64.log')),
    ('pkg.f26-x86_64',
     Platform('F26', 'F26 RPM',
              'Fedora 26 64-bit RPM build; Boost 1.63, gcc 7.1',
              rpm_vlong_header % "64-bit Fedora 26"
              + rpm_vlong_footer + "</p>",
              'package.fc26-x86_64.log')),
    ('pkg.f27-x86_64',
     Platform('F27', 'F27 RPM',
              'Fedora 27 64-bit RPM build; Boost 1.64, gcc 7.2',
              rpm_vlong_header % "64-bit Fedora 27"
              + rpm_vlong_footer + "</p>",
              'package.fc27-x86_64.log')),
    ('pkg.f28-x86_64',
     Platform('F28', 'F28 RPM',
              'Fedora 28 64-bit RPM build; Boost 1.66, gcc 8.0',
              rpm_vlong_header % "64-bit Fedora 28"
              + rpm_vlong_footer + "</p>",
              'package.fc28-x86_64.log')),
    ('pkg.f29-x86_64',
     Platform('F29', 'F29 RPM',
              'Fedora 29 64-bit RPM build; Boost 1.66, gcc 8.2',
              rpm_vlong_header % "64-bit Fedora 29"
              + rpm_vlong_footer + "</p>",
              'package.fc29-x86_64.log')),
    ('pkg.f30-x86_64',
     Platform('F30', 'F30 RPM',
              'Fedora 30 64-bit RPM build; Boost 1.69, gcc 9.0, '
              'Python 3',
              rpm_vlong_header % "64-bit Fedora 30"
              + rpm_vlong_footer + "</p>",
              'package.fc30-x86_64.log')),
    ('pkg.f31-x86_64',
     Platform('F31', 'F31 RPM',
              'Fedora 31 64-bit RPM build; Boost 1.69, gcc 9.2, '
              'Python 3',
              rpm_vlong_header % "64-bit Fedora 31"
              + rpm_vlong_footer + "</p>",
              'package.fc31-x86_64.log')),
    ('pkg.precise-x86_64',
     Platform('deb12', 'deb12',
              'Ubuntu 12.04 (Precise Pangolin) 64-bit package; '
              'Boost 1.48, gcc 4.6',
              ubuntu_vlong % "12.04 (Precise Pangolin)",
              'package.precise-x86_64.log')),
    ('pkg.trusty-x86_64',
     Platform('deb14', 'deb14',
              'Ubuntu 14.04 (Trusty Tahr) 64-bit package; '
              'Boost 1.54, gcc 4.8',
              ubuntu_vlong % "14.04 (Trusty Tahr)",
              'package.trusty-x86_64.log')),
    ('pkg.xenial-x86_64',
     Platform('deb16', 'deb16',
              'Ubuntu 16.04 (Xenial Xerus) 64-bit package; '
              'Boost 1.58, gcc 5.3',
              ubuntu_vlong % "16.04 (Xenial Xerus)",
              'package.xenial-x86_64.log')),
    ('pkg.bionic-x86_64',
     Platform('deb18', 'deb18',
              'Ubuntu 18.04 (Bionic Beaver) 64-bit package; '
              'Boost 1.65, gcc 7.2',
              ubuntu_vlong % "18.04 (Bionic Beaver)",
              'package.bionic-x86_64.log')),
    ('coverage',
     Platform('Cov', 'Coverage',
              'Coverage build (debug build on Fedora 31, 64-bit; '
              'Boost 1.69, gcc 9.2, Python 3)',
              coverage_vlong % ("64-bit Fedora 31", debug_build_vlong),
              'coverage.log')))
platforms_dict = dict(all_platforms)


def date_to_directory(date):
    """Convert a datetime.date object into the convention used to name
       directories on our system (e.g. '20120825')"""
    return date.strftime('%Y%m%d')


class _UnitSummary(object):
    def __init__(self, cur, test_fails, new_test_fails, build_info):
        self.data = summary = {}
        self.arch_ids = seen_archs = {}
        self.unit_ids = {}
        self.failed_archs = failed_archs = {}
        self.failed_units = failed_units = {}
        self.cmake_archs = {}
        for row in cur:
            self.unit_ids[row['unit_name']] = row['unit_id']
            seen_archs[row['arch_name']] = row['arch_id']
            archs = summary.get(row['unit_name'], None)
            if archs is None:
                summary[row['unit_name']] = archs = {}
            tf = test_fails.get((row['arch_id'], row['unit_id']), 0)
            ntf = new_test_fails.get((row['arch_id'], row['unit_id']), 0)
            archs[row['arch_name']] = {'state': row['state'],
                                       'logline': row['logline'],
                                       'lab_only': row['lab_only'],
                                       'numfails': tf,
                                       'numnewfails': ntf}
            if row['state'].startswith('CMAKE_'):
                self.cmake_archs[row['arch_name']] = None
            if row['state'] not in ('OK', 'SKIP', 'NOTEST', 'NOLOG',
                                    'CMAKE_OK', 'CMAKE_SKIP', 'CMAKE_FAILDEP',
                                    'CMAKE_NOBUILD', 'CMAKE_NOTEST',
                                    'CMAKE_NOEX', 'CMAKE_NOBENCH'):
                failed_archs[row['arch_name']] = None
                failed_units[row['unit_name']] = None
        self.all_units = self._sort_units(dict.fromkeys(summary.keys(), True),
                                          build_info)
        known_archs = [x[0] for x in all_platforms]
        self.all_archs = [x for x in known_archs if x in seen_archs] \
            + [x for x in seen_archs if x not in known_archs]

    def make_only_failed(self):
        self.all_units = [x for x in self.all_units if x in self.failed_units]
        self.all_archs = [x for x in self.all_archs if x in self.failed_archs]

    def _sort_units(self, unsorted_units, build_info):
        always_first = [['ALL'], ['ALL_LAB']]
        known_units = []
        for bi, first in zip(build_info, always_first):
            if bi:
                known_units.extend(first)
                for x in bi['modules']:
                    name = x['name']
                    if name == 'kernel':
                        name = 'IMP'
                    known_units.append(name)
                    known_units.append(name + ' benchmarks')
                    known_units.append(name + ' examples')

        sorted_units = []
        for u in known_units:
            if unsorted_units.pop(u, None):
                sorted_units.append(u)
            elif unsorted_units.pop('IMP.' + u, None):
                sorted_units.append('IMP.' + u)
        return sorted_units + list(unsorted_units.keys())


class BuildDatabase(object):
    def __init__(self, conn, config, date, lab_only, branch):
        self.conn = conn
        self.date = date
        self.lab_only = lab_only
        self.branch = branch
        self.__build_info = None
        self.public_topdir = os.path.join(config['TOPDIR'], branch)
        self.lab_only_topdir = os.path.join(config['LAB_ONLY_TOPDIR'], branch)
        self.topdir = self.lab_only_topdir if lab_only else self.public_topdir

    def get_sql_lab_only(self):
        """Get a suitable SQL WHERE fragment to restrict a query to only
           public units, if necessary"""
        if self.lab_only:
            return ""
        else:
            return " AND imp_test_units.lab_only=false"

    def get_branch_table(self, name):
        if self.branch == 'develop':
            return name
        else:
            return name + '_' + self.branch.replace('/', '_').replace('.', '_')

    def get_previous_build_date(self):
        """Get the date of the previous build, or None."""
        if self.branch == 'develop':
            # Assume develop branch is built every day
            return self.date - datetime.timedelta(days=1)
        else:
            # Query database to find last build date
            c = self.conn.cursor()
            table = self.get_branch_table('imp_test_reporev')
            query = 'SELECT date FROM ' + table \
                    + ' WHERE date<%s ORDER BY date DESC LIMIT 1'
            c.execute(query, (self.date,))
            row = c.fetchone()
            if row:
                return row[0]

    def get_unit_summary(self):
        c = MySQLdb.cursors.DictCursor(self.conn)
        table = self.get_branch_table('imp_test')
        query = 'SELECT arch,imp_test_names.unit,delta FROM ' + table \
                + ' imp_test,imp_test_names WHERE date=%s AND state NOT IN ' \
                + str(OK_STATES) + ' AND imp_test.name=imp_test_names.id'
        c.execute(query, (self.date,))
        test_fails = {}
        new_test_fails = {}
        for row in c:
            key = (row['arch'], row['unit'])
            test_fails[key] = test_fails.get(key, 0) + 1
            if row['delta'] == 'NEWFAIL':
                new_test_fails[key] = new_test_fails.get(key, 0) + 1

        table = self.get_branch_table('imp_test_unit_result')
        query = 'SELECT imp_test_archs.name AS arch_name, ' \
                'imp_test_units.lab_only, ' \
                'imp_test_unit_result.arch AS arch_id, ' \
                'imp_test_units.id AS unit_id, ' \
                'imp_test_units.name AS unit_name, ' \
                'imp_test_unit_result.state, ' \
                'imp_test_unit_result.logline FROM imp_test_archs, ' \
                'imp_test_units, ' + table + ' imp_test_unit_result WHERE ' \
                'imp_test_archs.id=imp_test_unit_result.arch AND ' \
                'imp_test_units.id=imp_test_unit_result.unit AND date=%s' \
                + self.get_sql_lab_only()
        c.execute(query, (self.date,))
        return _UnitSummary(c, test_fails, new_test_fails,
                            self.get_build_info())

    def get_doc_summary(self):
        """Get a summary of the doc build"""
        c = MySQLdb.cursors.DictCursor(self.conn)
        table = self.get_branch_table('imp_doc')
        query = "SELECT * FROM " + table + " WHERE date=%s"
        c.execute(query, (self.date,))
        return c.fetchone()

    def get_build_summary(self):
        """Get a one-word summary of the build"""
        c = self.conn.cursor()
        state_ind = 0
        # States ordered by severity
        states = ('OK', 'TEST', 'INCOMPLETE', 'BADLOG', 'BUILD')
        query = 'SELECT state FROM ' \
                + self.get_branch_table('imp_build_summary') + ' WHERE date=%s'
        if not self.lab_only:
            query += ' AND lab_only=false'
        c.execute(query, (self.date,))
        for row in c:
            # Report worst state
            state_ind = max(state_ind, states.index(row[0]))
        return states[state_ind]

    def get_last_build_with_summary(self, states):
        """Get the date of the last build with summary in the given state(s).
           Typically, states would be ('OK',) or ('OK','TEST').
           If no such build exists, None is returned."""
        sql = "(" + ",".join(repr(x) for x in states) + ")"
        sumtable = self.get_branch_table('imp_build_summary')
        # If including lab-only stuff, *both* public and lab-only builds must
        # be in the given state.
        if self.lab_only:
            query = "SELECT public.date FROM " + sumtable + " AS public, " \
                    + sumtable + " AS lab WHERE public.lab_only=false " \
                    "AND lab.lab_only=true AND public.date=lab.date AND " \
                    "lab.date<%s AND public.state IN " + sql + \
                    " AND lab.state IN " + sql
        else:
            query = "SELECT date FROM " + sumtable + " WHERE date<%s AND " \
                    "lab_only=false AND state IN " + sql
        query += " ORDER BY date DESC LIMIT 1"
        c = self.conn.cursor()
        c.execute(query, (self.date,))
        r = c.fetchone()
        if r:
            return r[0]

    def get_git_log(self):
        """Get the git log, as a list of objects, or None if no log exists."""
        _Log = collections.namedtuple('_Log', ['githash', 'author_name',
                                               'author_email', 'title'])
        g = os.path.join(self.topdir,
                         date_to_directory(self.date) + '-*', 'build',
                         'imp-gitlog')
        g = glob.glob(g)
        if len(g) > 0:
            data = []
            for line in open(g[0]):
                fields = line.rstrip('\r\n').split('\0')
                data.append(_Log._make(fields))
            return data

    def get_broken_links(self):
        """Get a filehandle to the broken links file."""
        g = os.path.join(self.topdir,
                         date_to_directory(self.date) + '-*', 'build',
                         'broken-links.html')
        g = glob.glob(g)
        if len(g) > 0:
            return open(g[0])

    def get_build_info(self):
        """Read in the build_info pickles for both public and lab-only builds,
           and return both. Either can be None if the pickle does not exist or
           we don't have permission to read it."""
        def get_pickle(t):
            g = os.path.join(t, date_to_directory(self.date) + '-*', 'build',
                             'build_info.pck')
            g = glob.glob(g)
            if len(g) > 0:
                with open(g[0], 'rb') as fh:
                    return pickle.load(fh)
        if self.__build_info is None:
            if self.lab_only:
                self.__build_info = (get_pickle(self.public_topdir),
                                     get_pickle(self.lab_only_topdir))
            else:
                self.__build_info = (get_pickle(self.public_topdir), None)
        return self.__build_info

    def get_all_component_tests(self, component, platform=None):
        platform_where = ''
        if platform:
            platform_where = 'AND imp_test.arch=%s '
        test = self.get_branch_table('imp_test')
        query = "SELECT imp_test_names.name AS test_name, imp_test.name, " \
                "imp_test.arch, imp_test_units.name AS unit_name, " \
                "imp_test_archs.name AS arch_name, imp_test.runtime, " \
                "imp_test.state, imp_test.delta, imp_test.detail FROM " \
                + test + " imp_test, " \
                "imp_test_names, imp_test_units, imp_test_archs WHERE " \
                "imp_test.date=%s AND imp_test_names.unit=%s " \
                + platform_where + \
                "AND imp_test.name=imp_test_names.id " \
                "AND imp_test_names.unit=imp_test_units.id AND " \
                "imp_test.arch=imp_test_archs.id" + self.get_sql_lab_only() \
                + " ORDER BY imp_test.state DESC,imp_test_units.name," \
                + "imp_test_names.id"
        if platform:
            return self._get_tests(query, (self.date, component, platform))
        else:
            return self._get_tests(query, (self.date, component))

    def get_all_failed_tests(self):
        test = self.get_branch_table('imp_test')
        query = "SELECT imp_test_names.name AS test_name, imp_test.name, " \
                "imp_test.arch, imp_test_units.name AS unit_name, " \
                "imp_test_names.unit AS unit_id, " \
                "imp_test_archs.name AS arch_name, imp_test.runtime, " \
                "imp_test.state, imp_test.delta, imp_test.detail FROM " \
                + test + " imp_test, " \
                "imp_test_names, imp_test_units, imp_test_archs WHERE " \
                "imp_test.date=%s AND imp_test.state NOT IN " \
                + str(OK_STATES) + " AND imp_test.name=imp_test_names.id " \
                "AND imp_test_names.unit=imp_test_units.id AND " \
                "imp_test.arch=imp_test_archs.id" + self.get_sql_lab_only() \
                + " ORDER BY imp_test_units.name,imp_test_names.id"
        return self._get_tests(query, (self.date,))

    def get_new_failed_tests(self):
        test = self.get_branch_table('imp_test')
        query = "SELECT imp_test_names.name AS test_name, imp_test.name, " \
                "imp_test.arch, imp_test_units.name AS unit_name, " \
                "imp_test_names.unit AS unit_id, " \
                "imp_test_archs.name AS arch_name, imp_test.runtime, " \
                "imp_test.state, imp_test.delta, imp_test.detail FROM " \
                + test + " imp_test, " \
                "imp_test_names, imp_test_units, imp_test_archs WHERE " \
                "imp_test.date=%s AND imp_test.delta='NEWFAIL' " \
                " AND imp_test.name=imp_test_names.id " \
                "AND imp_test_names.unit=imp_test_units.id AND " \
                "imp_test.arch=imp_test_archs.id" + self.get_sql_lab_only() \
                + " ORDER BY imp_test_units.name,imp_test_names.id"
        return self._get_tests(query, (self.date,))

    def get_long_tests(self):
        test = self.get_branch_table('imp_test')
        query = "SELECT imp_test_names.name AS test_name, imp_test.name, " \
                "imp_test.arch, imp_test_units.name AS unit_name, " \
                "imp_test_names.unit AS unit_id, " \
                "imp_test_archs.name AS arch_name, imp_test.runtime, " \
                "imp_test.state, imp_test.delta, imp_test.detail FROM " \
                + test + " imp_test, " \
                "imp_test_names, imp_test_units, imp_test_archs WHERE " \
                "imp_test.date=%s AND imp_test.runtime>20.0 AND " \
                "imp_test.name=imp_test_names.id AND " \
                "imp_test_names.unit=imp_test_units.id AND " \
                "imp_test.arch=imp_test_archs.id " + self.get_sql_lab_only() + \
                " ORDER BY imp_test.runtime DESC"
        return self._get_tests(query, (self.date,))

    def get_test_dict(self, date=None):
        """Get the state of every one of the day's tests, as a dict keyed by
           the test name and platform."""
        if date is None:
            date = self.date
        d = {}
        c = MySQLdb.cursors.DictCursor(self.conn)
        table = self.get_branch_table('imp_test')
        query = "SELECT name,arch,state FROM " + table + " WHERE date=%s"
        c.execute(query, (date,))
        for row in c:
            d[(row['name'], row['arch'])] = row['state']
        return d

    def _get_tests(self, query, args):
        c = MySQLdb.cursors.DictCursor(self.conn)
        c.execute(query, args)
        return c


def _text_format_build_summary(summary, unit, arch, arch_id):
    statemap = {'SKIP': 'skip',
                'OK': '-',
                'BUILD': 'BUILD',
                'BENCH': 'BENCH',
                'TEST': 'TEST',
                'NOTEST': '-',
                'NOLOG': '-',
                'UNCON': 'UNCON',
                'DISABLED': 'DISAB',
                'CMAKE_OK': '-',
                'CMAKE_BUILD': 'BUILD',
                'CMAKE_BENCH': 'BENCH',
                'CMAKE_TEST': 'TEST',
                'CMAKE_EXAMPLE': 'EXAMP',
                'CMAKE_NOBUILD': '-',
                'CMAKE_NOTEST': '-',
                'CMAKE_NOBENCH': '-',
                'CMAKE_NOEX': '-',
                'CMAKE_RUNBUILD': 'INCOM',
                'CMAKE_RUNTEST': 'INCOM',
                'CMAKE_RUNBENCH': 'INCOM',
                'CMAKE_RUNEX': 'INCOM',
                'CMAKE_CIRCDEP': 'BUILD',
                'CMAKE_FAILDEP': '-',
                'CMAKE_DISABLED': 'DISAB',
                'CMAKE_SKIP': 'skip'}
    try:
        s = summary[unit][arch]
    except KeyError:
        s = None
    if s is None:
        return 'skip'
    else:
        return statemap[s['state']]


def _short_unit_name(unit):
    if unit.startswith('IMP.'):
        return unit[4:]
    elif unit == 'IMP':
        return 'kernel'
    else:
        return unit


def send_imp_results_email(conn, msg_from, lab_only, branch):
    """Send out an email notification that new results are available."""
    import smtplib

    if lab_only:
        url = lab_only_results_url
        msg_to = 'imp-lab-build@salilab.org'
    else:
        url = results_url
        msg_to = 'imp-build@salilab.org'
    db = BuildDatabase(conn, datetime.date.today(), lab_only, branch)
    buildsum = db.get_build_summary()
    summary = db.get_unit_summary()
    log = db.get_git_log()
    doc = db.get_doc_summary()
    summary.make_only_failed()
    msg = MIMEText(_get_email_body(db, buildsum, summary, url, log, doc))
    msg['Keywords'] = ", ".join(["FAIL:" + _short_unit_name(x)
                                 for x in set(summary.failed_units)])
    msg['Subject'] = 'IMP nightly build results, %s' % db.date
    msg['Date'] = formatdate(localtime=True)
    msg['From'] = msg_from
    msg['To'] = msg_to
    s = smtplib.SMTP()
    s.connect()
    s.sendmail(msg_from, [msg_to], msg.as_string())
    s.close()


def _get_email_build_summary(buildsum):
    if buildsum == 'BUILD':
        return "At least part of IMP failed to build today.\n"
    elif buildsum == 'BADLOG':
        return "Something went wrong with the build system today, " \
               "so at least part\nof IMP was not adequately tested. " \
               "Use at your own risk!\n"
    elif buildsum == 'INCOMPLETE':
        return "The build system ran out of time on at least one " \
               "platform today.\n"
    else:
        return ''


def _get_email_body(db, buildsum, summary, url, log, doc):
    body = """IMP nightly build results, %s.
%sPlease see %s for
full details.

IMP component build summary (BUILD = failed to build;
BENCH = benchmarks failed to build or run;
INCOM = component did not complete building;
TEST = failed tests; EXAMP = failed examples;
DISAB = disabled due to wrong configuration;
UNCON = was not configured; skip = not built on this platform;
only components that failed on at least one platform are shown)
""" % (db.date, _get_email_build_summary(buildsum), url)
    body += " " * 18 + " ".join("%-5s" % platforms_dict[x].very_short
                                for x in summary.all_archs) + "\n"

    for row in summary.all_units:
        errs = [_text_format_build_summary(summary.data, row, col,
                                           summary.arch_ids[col])
                for col in summary.all_archs]
        body += "%-18s" % row[:18] + " ".join("%-5s" % e[:5] for e in errs) \
                + "\n"

    numfail = 0
    failed_units = {}
    for test in db.get_new_failed_tests():
        numfail += 1
        failed_units[test['unit_name']] = None
    if numfail > 0:
        body += "\nThere were %d new test failures (tests that passed " \
                "yesterday\n" % numfail \
                + "but failed today) in the following components:\n" \
                + "\n".join("   " + unit
                            for unit in sorted(failed_units.keys()))
    if doc:
        def _format_doc(title, nbroken):
            if nbroken > 0:
                if nbroken == 1:
                    suffix = ""
                else:
                    suffix = "s"
                return '\nToday\'s %s contains %d broken link%s.' \
                       % (title, nbroken, suffix)
            else:
                return ''
        body += _format_doc('manual', doc['nbroken_manual']) \
            + _format_doc('reference guide', doc['nbroken_tutorial']) \
            + _format_doc('RMF manual', doc['nbroken_rmf_manual'])
    if log:
        def _format_log(lm):
            txt = '%s %-10s %s' % (lm.githash[:10],
                                   lm.author_email.split('@')[0][:10],
                                   lm.title)
            return txt[:75]
        body += "\n\nChangelog:\n" + "\n".join(_format_log(lm) for lm in log)
    return body
